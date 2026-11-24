"""Staff workforce API: directory, invitations list/revoke, schedules,
attendance, leave. Reuses memberships and existing RBAC."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DBSession

from app.api.deps import get_db, require
from app.api.v1._shared import match_tenant
from app.modules.audit import service as audit_service
from app.modules.staff import schemas as S
from app.modules.staff import service as staff
from app.modules.staff.models import AttendanceRecord, LeaveRequest, LeaveType, StaffSchedule
from app.modules.tenancy.models import Membership
from app.platform.authz.permissions import P
from app.platform.authz.scope import RequestContext
from app.platform.errors import ForbiddenError, NotFoundError
from app.platform.request_context import request_id_ctx

router = APIRouter(tags=["staff"])


def _audit(
    db: DBSession, ctx: RequestContext, *, action: str, rtype: str, rid: str
) -> None:
    audit_service.append(
        db,
        tenant_id=ctx.tenant_id,
        actor_type="user",
        actor_id=str(ctx.user_id),
        action=action,
        resource_type=rtype,
        resource_id=rid,
        request_id=request_id_ctx.get(),
    )


def _member(d: dict[str, object]) -> S.StaffMemberResponse:
    return S.StaffMemberResponse.model_validate(d)


def _schedule(row: StaffSchedule) -> S.ScheduleResponse:
    return S.ScheduleResponse(
        id=row.id,
        membership_id=row.membership_id,
        location_id=row.location_id,
        weekday=row.weekday,
        start_time=row.start_time,
        end_time=row.end_time,
        break_minutes=row.break_minutes,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        is_active=row.is_active,
    )


def _attendance(row: AttendanceRecord) -> S.AttendanceResponse:
    return S.AttendanceResponse.model_validate(staff.attendance_to_dict(row))


def _leave(row: LeaveRequest, lt: LeaveType) -> S.LeaveResponse:
    return S.LeaveResponse(
        id=row.id,
        membership_id=row.membership_id,
        leave_type_id=row.leave_type_id,
        leave_type_name=lt.name,
        start_date=row.start_date,
        end_date=row.end_date,
        reason=row.reason,
        status=row.status,
        decided_by=row.decided_by,
        decided_at=row.decided_at,
        decision_note=row.decision_note,
        created_at=row.created_at,
    )


def _own_membership(db: DBSession, ctx: RequestContext) -> Membership:
    m = db.get(Membership, ctx.membership_id)
    if m is None or m.tenant_id != ctx.tenant_id or m.user_id != ctx.user_id:
        raise ForbiddenError("no active membership")
    return m


# --- Directory ---


@router.get("/tenants/{tenant_id}/staff", response_model=list[S.StaffMemberResponse])
def list_staff(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.STAFF_MANAGE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    q: str | None = None,
    active_only: bool = False,
    location_id: uuid.UUID | None = None,
) -> list[S.StaffMemberResponse]:
    match_tenant(ctx, tenant_id)
    rows = staff.list_staff(
        db, tenant_id=tenant_id, q=q, active_only=active_only, location_id=location_id
    )
    return [_member(r) for r in rows]


@router.get(
    "/tenants/{tenant_id}/staff/{membership_id}",
    response_model=S.StaffMemberResponse,
)
def get_staff(
    tenant_id: uuid.UUID,
    membership_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.STAFF_MANAGE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.StaffMemberResponse:
    match_tenant(ctx, tenant_id)
    return _member(staff.get_staff_member(db, tenant_id=tenant_id, membership_id=membership_id))


@router.patch(
    "/tenants/{tenant_id}/staff/{membership_id}",
    response_model=S.StaffMemberResponse,
)
def patch_staff(
    tenant_id: uuid.UUID,
    membership_id: uuid.UUID,
    body: S.StaffProfileUpdateRequest,
    ctx: RequestContext = Depends(require(P.STAFF_MANAGE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.StaffMemberResponse:
    match_tenant(ctx, tenant_id)
    updated = staff.update_staff_profile(
        db,
        tenant_id=tenant_id,
        membership_id=membership_id,
        designation=body.designation,
        phone=body.phone,
        employment_status=body.employment_status,
        joined_at=body.joined_at,
        notes=body.notes,
        location_ids=body.location_ids,
        role_name=body.role,
        is_active=body.is_active,
    )
    _audit(db, ctx, action="staff.profile.update", rtype="membership", rid=str(membership_id))
    return _member(updated)


# --- Invitations list / revoke ---


@router.get(
    "/tenants/{tenant_id}/invitations",
    response_model=list[S.InvitationListItem],
)
def list_invitations(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.STAFF_INVITE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    status: str | None = None,
) -> list[S.InvitationListItem]:
    match_tenant(ctx, tenant_id)
    rows = staff.list_invitations(db, tenant_id=tenant_id, status=status)
    return [
        S.InvitationListItem(
            id=inv.id,
            email=inv.email,
            role=role.name,
            status=inv.status,
            location_ids=staff.invitation_location_ids(inv),
            expires_at=inv.expires_at,
            created_at=inv.created_at,
            invited_by=inv.invited_by,
        )
        for inv, role in rows
    ]


@router.post("/tenants/{tenant_id}/invitations/{invitation_id}/revoke")
def revoke_invitation(
    tenant_id: uuid.UUID,
    invitation_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.STAFF_INVITE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> dict[str, str]:
    match_tenant(ctx, tenant_id)
    inv = staff.revoke_invitation(db, tenant_id=tenant_id, invitation_id=invitation_id)
    _audit(db, ctx, action="invite.revoke", rtype="invitation", rid=str(inv.id))
    return {"status": "revoked"}


# --- Schedules ---


@router.post(
    "/tenants/{tenant_id}/staff-schedules",
    response_model=S.ScheduleResponse,
)
def create_schedule(
    tenant_id: uuid.UUID,
    body: S.ScheduleCreateRequest,
    ctx: RequestContext = Depends(require(P.STAFF_MANAGE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.ScheduleResponse:
    match_tenant(ctx, tenant_id)
    row = staff.create_schedule(
        db,
        tenant_id=tenant_id,
        membership_id=body.membership_id,
        location_id=body.location_id,
        weekday=body.weekday,
        start_time=body.start_time,
        end_time=body.end_time,
        break_minutes=body.break_minutes,
        effective_from=body.effective_from,
        effective_to=body.effective_to,
    )
    _audit(db, ctx, action="staff.schedule.create", rtype="staff_schedule", rid=str(row.id))
    return _schedule(row)


@router.get(
    "/tenants/{tenant_id}/staff-schedules",
    response_model=list[S.ScheduleResponse],
)
def list_schedules(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.STAFF_MANAGE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    membership_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
) -> list[S.ScheduleResponse]:
    match_tenant(ctx, tenant_id)
    rows = staff.list_schedules(
        db, tenant_id=tenant_id, membership_id=membership_id, location_id=location_id
    )
    return [_schedule(r) for r in rows]


@router.post("/tenants/{tenant_id}/staff-schedules/{schedule_id}/deactivate")
def deactivate_schedule(
    tenant_id: uuid.UUID,
    schedule_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.STAFF_MANAGE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> dict[str, str]:
    match_tenant(ctx, tenant_id)
    row = staff.deactivate_schedule(db, tenant_id=tenant_id, schedule_id=schedule_id)
    _audit(db, ctx, action="staff.schedule.deactivate", rtype="staff_schedule", rid=str(row.id))
    return {"status": "deactivated"}


# --- Attendance ---


@router.post(
    "/tenants/{tenant_id}/attendance/check-in",
    response_model=S.AttendanceResponse,
)
def check_in(
    tenant_id: uuid.UUID,
    body: S.CheckInRequest,
    ctx: RequestContext = Depends(require(P.TENANT_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.AttendanceResponse:
    match_tenant(ctx, tenant_id)
    m = _own_membership(db, ctx)
    row = staff.check_in(
        db,
        tenant_id=tenant_id,
        membership_id=m.id,
        location_id=body.location_id,
        actor_user_id=ctx.user_id,
    )
    _audit(db, ctx, action="attendance.check_in", rtype="attendance", rid=str(row.id))
    return _attendance(row)


@router.post(
    "/tenants/{tenant_id}/attendance/check-out",
    response_model=S.AttendanceResponse,
)
def check_out(
    tenant_id: uuid.UUID,
    body: S.CheckOutRequest,
    ctx: RequestContext = Depends(require(P.TENANT_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.AttendanceResponse:
    match_tenant(ctx, tenant_id)
    m = _own_membership(db, ctx)
    row = staff.check_out(
        db,
        tenant_id=tenant_id,
        membership_id=m.id,
        actor_user_id=ctx.user_id,
        attendance_id=body.attendance_id,
    )
    _audit(db, ctx, action="attendance.check_out", rtype="attendance", rid=str(row.id))
    return _attendance(row)


@router.get(
    "/tenants/{tenant_id}/attendance",
    response_model=list[S.AttendanceResponse],
)
def list_attendance(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.TENANT_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    membership_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[S.AttendanceResponse]:
    match_tenant(ctx, tenant_id)
    own = _own_membership(db, ctx)
    # Non-managers only see their own attendance.
    if P.STAFF_MANAGE not in ctx.permissions:
        membership_id = own.id
    rows = staff.list_attendance(
        db,
        tenant_id=tenant_id,
        membership_id=membership_id,
        location_id=location_id,
        from_date=from_date,
        to_date=to_date,
    )
    return [_attendance(r) for r in rows]


@router.post(
    "/tenants/{tenant_id}/attendance/{attendance_id}/correct",
    response_model=S.AttendanceResponse,
)
def correct_attendance(
    tenant_id: uuid.UUID,
    attendance_id: uuid.UUID,
    body: S.AttendanceCorrectRequest,
    ctx: RequestContext = Depends(require(P.STAFF_MANAGE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.AttendanceResponse:
    match_tenant(ctx, tenant_id)
    row = staff.correct_attendance(
        db,
        tenant_id=tenant_id,
        attendance_id=attendance_id,
        actor_user_id=ctx.user_id,
        check_in_at=body.check_in_at,
        check_out_at=body.check_out_at,
        reason=body.reason,
    )
    _audit(db, ctx, action="attendance.correct", rtype="attendance", rid=str(row.id))
    return _attendance(row)


# --- Leave ---


@router.get(
    "/tenants/{tenant_id}/leave-types",
    response_model=list[S.LeaveTypeResponse],
)
def list_leave_types(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.TENANT_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> list[S.LeaveTypeResponse]:
    match_tenant(ctx, tenant_id)
    rows = staff.list_leave_types(db, tenant_id=tenant_id)
    return [S.LeaveTypeResponse(id=r.id, name=r.name, is_active=r.is_active) for r in rows]


@router.post(
    "/tenants/{tenant_id}/leave-types",
    response_model=S.LeaveTypeResponse,
)
def create_leave_type(
    tenant_id: uuid.UUID,
    body: S.LeaveTypeCreateRequest,
    ctx: RequestContext = Depends(require(P.STAFF_MANAGE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.LeaveTypeResponse:
    match_tenant(ctx, tenant_id)
    row = staff.create_leave_type(db, tenant_id=tenant_id, name=body.name)
    _audit(db, ctx, action="leave.type.create", rtype="leave_type", rid=str(row.id))
    return S.LeaveTypeResponse(id=row.id, name=row.name, is_active=row.is_active)


@router.post(
    "/tenants/{tenant_id}/leave-requests",
    response_model=S.LeaveResponse,
)
def create_leave(
    tenant_id: uuid.UUID,
    body: S.LeaveCreateRequest,
    ctx: RequestContext = Depends(require(P.TENANT_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.LeaveResponse:
    match_tenant(ctx, tenant_id)
    m = _own_membership(db, ctx)
    row = staff.create_leave_request(
        db,
        tenant_id=tenant_id,
        membership_id=m.id,
        leave_type_id=body.leave_type_id,
        start_date=body.start_date,
        end_date=body.end_date,
        reason=body.reason,
    )
    lt = db.get(LeaveType, row.leave_type_id)
    assert lt is not None
    _audit(db, ctx, action="leave.request", rtype="leave_request", rid=str(row.id))
    return _leave(row, lt)


@router.get(
    "/tenants/{tenant_id}/leave-requests",
    response_model=list[S.LeaveResponse],
)
def list_leave(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.TENANT_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    membership_id: uuid.UUID | None = None,
    status: str | None = None,
) -> list[S.LeaveResponse]:
    match_tenant(ctx, tenant_id)
    own = _own_membership(db, ctx)
    if P.STAFF_MANAGE not in ctx.permissions:
        membership_id = own.id
    rows = staff.list_leave(
        db, tenant_id=tenant_id, membership_id=membership_id, status=status
    )
    return [_leave(r, lt) for r, lt in rows]


@router.post(
    "/tenants/{tenant_id}/leave-requests/{leave_id}/decide",
    response_model=S.LeaveResponse,
)
def decide_leave(
    tenant_id: uuid.UUID,
    leave_id: uuid.UUID,
    body: S.LeaveDecideRequest,
    ctx: RequestContext = Depends(require(P.STAFF_MANAGE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.LeaveResponse:
    match_tenant(ctx, tenant_id)
    row = staff.decide_leave(
        db,
        tenant_id=tenant_id,
        leave_id=leave_id,
        actor_user_id=ctx.user_id,
        decision=body.decision,
        note=body.note,
    )
    lt = db.get(LeaveType, row.leave_type_id)
    if lt is None:
        raise NotFoundError("leave type not found")
    _audit(db, ctx, action=f"leave.{body.decision}", rtype="leave_request", rid=str(row.id))
    return _leave(row, lt)
