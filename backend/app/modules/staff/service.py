"""Staff workforce services: directory, invitations helpers, schedules,
attendance, leave. Membership remains the employment relationship.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.modules.clinics.models import Location
from app.modules.identity.models import User
from app.modules.staff.models import (
    ATT_SOURCE_MANUAL,
    ATT_SOURCE_SELF,
    EMP_ACTIVE,
    LEAVE_APPROVED,
    LEAVE_CANCELLED,
    LEAVE_PENDING,
    LEAVE_REJECTED,
    AttendanceRecord,
    LeaveRequest,
    LeaveType,
    StaffProfile,
    StaffSchedule,
)
from app.modules.tenancy import service as tenancy_service
from app.modules.tenancy.models import Invitation, Membership, Role
from app.platform import ids
from app.platform.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.platform.time import UTC, now


def _get_membership(db: DBSession, *, tenant_id: uuid.UUID, membership_id: uuid.UUID) -> Membership:
    m = db.get(Membership, membership_id)
    if m is None or m.tenant_id != tenant_id:
        raise NotFoundError("membership not found")
    return m


def _get_location(db: DBSession, *, tenant_id: uuid.UUID, location_id: uuid.UUID) -> Location:
    loc = db.get(Location, location_id)
    if loc is None or loc.tenant_id != tenant_id:
        raise ForbiddenError("location is outside this tenant")
    return loc


def _ensure_profile(db: DBSession, membership: Membership) -> StaffProfile:
    row = db.get(StaffProfile, membership.id)
    if row is not None:
        return row
    ts = now()
    row = StaffProfile(
        membership_id=membership.id,
        tenant_id=membership.tenant_id,
        designation=None,
        phone=None,
        employment_status=EMP_ACTIVE,
        joined_at=membership.created_at.date() if membership.created_at else None,
        notes=None,
        created_at=ts,
        updated_at=ts,
    )
    db.add(row)
    db.flush()
    return row


def list_staff(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    q: str | None = None,
    active_only: bool = False,
    location_id: uuid.UUID | None = None,
) -> list[dict[str, object]]:
    rows = db.execute(
        select(Membership, Role, User)
        .join(Role, Membership.role_id == Role.id)
        .join(User, Membership.user_id == User.id)
        .where(Membership.tenant_id == tenant_id)
        .order_by(User.display_name)
    ).all()
    out: list[dict[str, object]] = []
    needle = (q or "").strip().lower()
    for m, role, user in rows:
        if active_only and not m.is_active:
            continue
        locs = tenancy_service.membership_location_ids(db, m.id)
        if location_id is not None and locs and location_id not in locs:
            continue
        if needle and needle not in user.email.lower() and needle not in user.display_name.lower():
            profile = db.get(StaffProfile, m.id)
            des = (profile.designation or "").lower() if profile else ""
            if needle not in des:
                continue
        profile = _ensure_profile(db, m)
        out.append(
            {
                "membership_id": m.id,
                "user_id": user.id,
                "email": user.email,
                "display_name": user.display_name,
                "role": role.name,
                "permissions": list(role.permissions or []),
                "is_active": m.is_active,
                "is_primary": m.is_primary,
                "location_ids": locs,
                "designation": profile.designation,
                "phone": profile.phone,
                "employment_status": profile.employment_status,
                "joined_at": profile.joined_at,
                "notes": profile.notes,
            }
        )
    return out


def get_staff_member(
    db: DBSession, *, tenant_id: uuid.UUID, membership_id: uuid.UUID
) -> dict[str, object]:
    m = _get_membership(db, tenant_id=tenant_id, membership_id=membership_id)
    role = db.get(Role, m.role_id)
    user = db.get(User, m.user_id)
    if role is None or user is None:
        raise NotFoundError("membership not found")
    profile = _ensure_profile(db, m)
    return {
        "membership_id": m.id,
        "user_id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": role.name,
        "permissions": list(role.permissions or []),
        "is_active": m.is_active,
        "is_primary": m.is_primary,
        "location_ids": tenancy_service.membership_location_ids(db, m.id),
        "designation": profile.designation,
        "phone": profile.phone,
        "employment_status": profile.employment_status,
        "joined_at": profile.joined_at,
        "notes": profile.notes,
    }


def update_staff_profile(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    membership_id: uuid.UUID,
    designation: str | None = None,
    phone: str | None = None,
    employment_status: str | None = None,
    joined_at: date | None = None,
    notes: str | None = None,
    location_ids: list[uuid.UUID] | None = None,
    role_name: str | None = None,
    is_active: bool | None = None,
) -> dict[str, object]:
    m = _get_membership(db, tenant_id=tenant_id, membership_id=membership_id)
    role = None
    if role_name is not None:
        role = db.execute(
            select(Role).where(
                ((Role.tenant_id.is_(None)) | (Role.tenant_id == tenant_id))
                & (Role.name == role_name)
            )
        ).scalar_one_or_none()
        if role is None:
            raise NotFoundError("role not found")
    if role is not None or is_active is not None or location_ids is not None:
        tenancy_service.update_membership(
            db,
            membership=m,
            role=role,
            is_active=is_active,
            location_ids=location_ids,
        )
        db.refresh(m)
    profile = _ensure_profile(db, m)
    if designation is not None:
        profile.designation = designation.strip() or None
    if phone is not None:
        profile.phone = phone.strip() or None
    if employment_status is not None:
        profile.employment_status = employment_status
    if joined_at is not None:
        profile.joined_at = joined_at
    if notes is not None:
        profile.notes = notes.strip() or None
    profile.updated_at = now()
    return get_staff_member(db, tenant_id=tenant_id, membership_id=membership_id)


# --- Invitations (list / revoke; create stays in tenancy) ---


def invitation_location_ids(inv: Invitation) -> list[uuid.UUID]:
    raw = getattr(inv, "location_ids_json", None)
    if not raw:
        return []
    try:
        return [uuid.UUID(str(x)) for x in json.loads(raw)]
    except (TypeError, ValueError, json.JSONDecodeError):
        return []


def list_invitations(
    db: DBSession, *, tenant_id: uuid.UUID, status: str | None = None
) -> list[tuple[Invitation, Role]]:
    stmt = (
        select(Invitation, Role)
        .join(Role, Invitation.role_id == Role.id)
        .where(Invitation.tenant_id == tenant_id)
        .order_by(Invitation.created_at.desc())
    )
    if status:
        stmt = stmt.where(Invitation.status == status)
    return [(inv, role) for inv, role in db.execute(stmt).all()]


def revoke_invitation(
    db: DBSession, *, tenant_id: uuid.UUID, invitation_id: uuid.UUID
) -> Invitation:
    inv = db.get(Invitation, invitation_id)
    if inv is None or inv.tenant_id != tenant_id:
        raise NotFoundError("invitation not found")
    if inv.status != "pending":
        raise ConflictError("invitation is not pending")
    inv.status = "revoked"
    return inv


def accept_invitation_authenticated(
    db: DBSession, *, token: str, user: User
) -> Membership:
    """Bind a pending invite to an already-authenticated user. Email must match.
    Does not set or share passwords."""
    import hashlib

    digest = hashlib.sha256(token.encode()).hexdigest()
    inv = db.execute(
        select(Invitation).where(Invitation.token_hash == digest).with_for_update()
    ).scalar_one_or_none()
    if inv is None or inv.status != "pending" or inv.expires_at <= now():
        from app.platform.errors import GoneError

        raise GoneError("invitation invalid or expired")
    if user.email.lower() != inv.email.lower():
        raise ForbiddenError("invitation email does not match authenticated user")
    if not user.is_active:
        raise ForbiddenError("user is deactivated")
    tenant = tenancy_service.get_tenant(db, inv.tenant_id)
    if tenant.status != "active":
        raise ForbiddenError("tenant is not active")
    role = db.get(Role, inv.role_id)
    if role is None:
        from app.platform.errors import GoneError

        raise GoneError("invitation role no longer exists")
    locs = invitation_location_ids(inv)
    membership = tenancy_service.create_membership(
        db,
        user=user,
        tenant=tenant,
        role=role,
        location_ids=locs or None,
        converting_invitation_id=inv.id,
    )
    inv.status = "accepted"
    inv.accepted_at = now()
    return membership


# --- Schedules ---


def create_schedule(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    membership_id: uuid.UUID,
    location_id: uuid.UUID,
    weekday: int,
    start_time: time,
    end_time: time,
    break_minutes: int,
    effective_from: date,
    effective_to: date | None,
) -> StaffSchedule:
    from app.modules.subscriptions.commercial_policy import assert_feature

    assert_feature(
        db, tenant_id=tenant_id, feature_key="staff_workforce", operation="staff.schedule.create"
    )
    m = _get_membership(db, tenant_id=tenant_id, membership_id=membership_id)
    _get_location(db, tenant_id=tenant_id, location_id=location_id)
    if end_time <= start_time:
        raise ValidationError("end_time must be after start_time")
    if effective_to is not None and effective_to < effective_from:
        raise ValidationError("effective_to must be on or after effective_from")
    ts = now()
    row = StaffSchedule(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        membership_id=m.id,
        location_id=location_id,
        weekday=weekday,
        start_time=start_time,
        end_time=end_time,
        break_minutes=break_minutes,
        effective_from=effective_from,
        effective_to=effective_to,
        is_active=True,
        created_at=ts,
        updated_at=ts,
    )
    db.add(row)
    db.flush()
    return row


def list_schedules(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    membership_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
) -> list[StaffSchedule]:
    stmt = select(StaffSchedule).where(
        StaffSchedule.tenant_id == tenant_id, StaffSchedule.is_active.is_(True)
    )
    if membership_id is not None:
        stmt = stmt.where(StaffSchedule.membership_id == membership_id)
    if location_id is not None:
        stmt = stmt.where(StaffSchedule.location_id == location_id)
    ordered = stmt.order_by(StaffSchedule.weekday, StaffSchedule.start_time)
    return list(db.execute(ordered).scalars())


def deactivate_schedule(
    db: DBSession, *, tenant_id: uuid.UUID, schedule_id: uuid.UUID
) -> StaffSchedule:
    row = db.get(StaffSchedule, schedule_id)
    if row is None or row.tenant_id != tenant_id:
        raise NotFoundError("schedule not found")
    row.is_active = False
    row.updated_at = now()
    return row


# --- Attendance ---


def _duration_minutes(row: AttendanceRecord) -> int | None:
    if row.check_out_at is None:
        return None
    delta = row.check_out_at - row.check_in_at
    return max(0, int(delta.total_seconds() // 60))


def check_in(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    membership_id: uuid.UUID,
    location_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    source: str = ATT_SOURCE_SELF,
) -> AttendanceRecord:
    m = _get_membership(db, tenant_id=tenant_id, membership_id=membership_id)
    if not m.is_active:
        raise ForbiddenError("membership is inactive")
    if source == ATT_SOURCE_SELF and m.user_id != actor_user_id:
        raise ForbiddenError("cannot check in for another staff member")
    _get_location(db, tenant_id=tenant_id, location_id=location_id)
    # Lock any open attendance for this membership.
    open_row = db.execute(
        select(AttendanceRecord)
        .where(
            AttendanceRecord.membership_id == membership_id,
            AttendanceRecord.check_out_at.is_(None),
        )
        .with_for_update()
    ).scalar_one_or_none()
    if open_row is not None:
        raise ConflictError("already checked in; check out first")
    ts = now()
    row = AttendanceRecord(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        membership_id=membership_id,
        location_id=location_id,
        attendance_date=ts.astimezone(UTC).date(),
        check_in_at=ts,
        check_out_at=None,
        source=source,
        corrected_by=None,
        correction_reason=None,
        created_at=ts,
        updated_at=ts,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        raise ConflictError("already checked in; check out first") from exc
    return row


def check_out(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    membership_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    attendance_id: uuid.UUID | None = None,
    allow_manager: bool = False,
) -> AttendanceRecord:
    m = _get_membership(db, tenant_id=tenant_id, membership_id=membership_id)
    if not allow_manager and m.user_id != actor_user_id:
        raise ForbiddenError("cannot check out for another staff member")
    stmt = (
        select(AttendanceRecord)
        .where(
            AttendanceRecord.tenant_id == tenant_id,
            AttendanceRecord.membership_id == membership_id,
            AttendanceRecord.check_out_at.is_(None),
        )
        .with_for_update()
    )
    if attendance_id is not None:
        stmt = stmt.where(AttendanceRecord.id == attendance_id)
    row = db.execute(stmt).scalar_one_or_none()
    if row is None:
        raise ConflictError("no open check-in to close")
    ts = now()
    if ts <= row.check_in_at:
        raise ValidationError("check-out must be after check-in")
    row.check_out_at = ts
    row.updated_at = ts
    return row


def correct_attendance(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    attendance_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    check_in_at: datetime | None,
    check_out_at: datetime | None,
    reason: str,
) -> AttendanceRecord:
    row = db.get(AttendanceRecord, attendance_id)
    if row is None or row.tenant_id != tenant_id:
        raise NotFoundError("attendance not found")
    # Lock row for concurrent correction safety.
    locked = db.execute(
        select(AttendanceRecord)
        .where(AttendanceRecord.id == attendance_id)
        .with_for_update()
    ).scalar_one()
    new_in = check_in_at or locked.check_in_at
    new_out = check_out_at if check_out_at is not None else locked.check_out_at
    if new_in.tzinfo is None:
        new_in = new_in.replace(tzinfo=UTC)
    if new_out is not None and new_out.tzinfo is None:
        new_out = new_out.replace(tzinfo=UTC)
    if new_out is not None and new_out <= new_in:
        raise ValidationError("check-out must be after check-in")
    locked.check_in_at = new_in
    locked.check_out_at = new_out
    locked.attendance_date = new_in.astimezone(UTC).date()
    locked.source = ATT_SOURCE_MANUAL
    locked.corrected_by = actor_user_id
    locked.correction_reason = reason.strip()
    locked.updated_at = now()
    return locked


def list_attendance(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    membership_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    limit: int = 100,
) -> list[AttendanceRecord]:
    stmt = select(AttendanceRecord).where(AttendanceRecord.tenant_id == tenant_id)
    if membership_id is not None:
        stmt = stmt.where(AttendanceRecord.membership_id == membership_id)
    if location_id is not None:
        stmt = stmt.where(AttendanceRecord.location_id == location_id)
    if from_date is not None:
        stmt = stmt.where(AttendanceRecord.attendance_date >= from_date)
    if to_date is not None:
        stmt = stmt.where(AttendanceRecord.attendance_date <= to_date)
    return list(
        db.execute(
            stmt.order_by(AttendanceRecord.check_in_at.desc()).limit(min(limit, 500))
        ).scalars()
    )


# --- Leave ---


def ensure_default_leave_types(db: DBSession, *, tenant_id: uuid.UUID) -> list[LeaveType]:
    existing = list(
        db.execute(select(LeaveType).where(LeaveType.tenant_id == tenant_id)).scalars()
    )
    if existing:
        return existing
    ts = now()
    created: list[LeaveType] = []
    for name in ("Annual", "Sick", "Unpaid"):
        row = LeaveType(
            id=ids.uuid7(),
            tenant_id=tenant_id,
            name=name,
            is_active=True,
            created_at=ts,
        )
        db.add(row)
        created.append(row)
    db.flush()
    return created


def create_leave_type(db: DBSession, *, tenant_id: uuid.UUID, name: str) -> LeaveType:
    row = LeaveType(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        name=name.strip(),
        is_active=True,
        created_at=now(),
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        raise ConflictError("leave type already exists") from exc
    return row


def list_leave_types(db: DBSession, *, tenant_id: uuid.UUID) -> list[LeaveType]:
    ensure_default_leave_types(db, tenant_id=tenant_id)
    return list(
        db.execute(
            select(LeaveType)
            .where(LeaveType.tenant_id == tenant_id, LeaveType.is_active.is_(True))
            .order_by(LeaveType.name)
        ).scalars()
    )


def create_leave_request(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    membership_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    start_date: date,
    end_date: date,
    reason: str | None,
) -> LeaveRequest:
    m = _get_membership(db, tenant_id=tenant_id, membership_id=membership_id)
    if not m.is_active:
        raise ForbiddenError("membership is inactive")
    lt = db.get(LeaveType, leave_type_id)
    if lt is None or lt.tenant_id != tenant_id or not lt.is_active:
        raise NotFoundError("leave type not found")
    if end_date < start_date:
        raise ValidationError("end_date must be on or after start_date")
    ts = now()
    row = LeaveRequest(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        membership_id=membership_id,
        leave_type_id=leave_type_id,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
        status=LEAVE_PENDING,
        decided_by=None,
        decided_at=None,
        decision_note=None,
        created_at=ts,
        updated_at=ts,
    )
    db.add(row)
    db.flush()
    return row


def decide_leave(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    leave_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    decision: str,
    note: str | None,
) -> LeaveRequest:
    row = db.execute(
        select(LeaveRequest)
        .where(LeaveRequest.id == leave_id, LeaveRequest.tenant_id == tenant_id)
        .with_for_update()
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("leave request not found")
    if row.status != LEAVE_PENDING:
        raise ConflictError("leave request is not pending")
    m = _get_membership(db, tenant_id=tenant_id, membership_id=row.membership_id)
    if m.user_id == actor_user_id:
        raise ForbiddenError("cannot approve or reject your own leave request")
    if decision not in (LEAVE_APPROVED, LEAVE_REJECTED):
        raise ValidationError("invalid decision")
    row.status = decision
    row.decided_by = actor_user_id
    row.decided_at = now()
    row.decision_note = note
    row.updated_at = now()
    return row


def cancel_leave(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    leave_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> LeaveRequest:
    row = db.get(LeaveRequest, leave_id)
    if row is None or row.tenant_id != tenant_id:
        raise NotFoundError("leave request not found")
    m = _get_membership(db, tenant_id=tenant_id, membership_id=row.membership_id)
    if m.user_id != actor_user_id:
        raise ForbiddenError("only the requester can cancel")
    if row.status != LEAVE_PENDING:
        raise ConflictError("only pending leave can be cancelled")
    row.status = LEAVE_CANCELLED
    row.updated_at = now()
    return row


def list_leave(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    membership_id: uuid.UUID | None = None,
    status: str | None = None,
) -> list[tuple[LeaveRequest, LeaveType]]:
    stmt = (
        select(LeaveRequest, LeaveType)
        .join(LeaveType, LeaveRequest.leave_type_id == LeaveType.id)
        .where(LeaveRequest.tenant_id == tenant_id)
        .order_by(LeaveRequest.created_at.desc())
    )
    if membership_id is not None:
        stmt = stmt.where(LeaveRequest.membership_id == membership_id)
    if status is not None:
        stmt = stmt.where(LeaveRequest.status == status)
    return [(req, lt) for req, lt in db.execute(stmt).all()]


def attendance_to_dict(row: AttendanceRecord) -> dict[str, object]:
    return {
        "id": row.id,
        "membership_id": row.membership_id,
        "location_id": row.location_id,
        "attendance_date": row.attendance_date,
        "check_in_at": row.check_in_at,
        "check_out_at": row.check_out_at,
        "source": row.source,
        "correction_reason": row.correction_reason,
        "duration_minutes": _duration_minutes(row),
    }
