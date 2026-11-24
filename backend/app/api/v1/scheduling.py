"""Scheduling endpoints. Thin adapters over the scheduling service:

- tenant match (404-oracle) + permission gate on every route
- location scope translated from the RequestContext, enforced in the service
- audit appended per significant action (refs only, never notes/content)
- confirmation notification requested on create when the patient has a
  contact channel (existing notification.requested outbox flow, refs only)

Domain rules (transitions, overlap, timezone) live in the service, never here.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session as DBSession

from app.api.deps import get_db, require
from app.api.v1._shared import match_tenant
from app.modules.audit import service as audit_service
from app.modules.notifications import service as notify_service
from app.modules.patients import service as patients_service
from app.modules.scheduling import schemas as S
from app.modules.scheduling import service as sched
from app.modules.scheduling.models import Appointment
from app.platform.authz.permissions import P
from app.platform.authz.scope import RequestContext
from app.platform.ports.ports import NotifyRequest
from app.platform.request_context import request_id_ctx

router = APIRouter(tags=["scheduling"])


def _audit(db: DBSession, ctx: RequestContext, *, action: str, rid: str) -> None:
    audit_service.append(
        db,
        tenant_id=ctx.tenant_id,
        actor_type="user",
        actor_id=str(ctx.user_id),
        action=action,
        resource_type="appointment",
        resource_id=rid,
        request_id=request_id_ctx.get(),
    )


def _resp(a: Appointment) -> S.AppointmentResponse:
    return S.AppointmentResponse(
        id=a.id,
        tenant_id=a.tenant_id,
        patient_id=a.patient_id,
        practitioner_id=a.practitioner_id,
        location_id=a.location_id,
        start_at=a.start_at,
        end_at=a.end_at,
        timezone=a.timezone,
        status=a.status,
        notes=a.notes,
        queue_token=a.queue_token,
        queue_date=a.queue_date,
        cancelled_at=a.cancelled_at,
        cancelled_by=a.cancelled_by,
        cancel_reason=a.cancel_reason,
        created_at=a.created_at,
        updated_at=a.updated_at,
    )


def _bucket_queue(
    items: list[Appointment],
) -> tuple[
    list[S.AppointmentResponse],
    list[S.AppointmentResponse],
    list[S.AppointmentResponse],
    list[S.AppointmentResponse],
    list[S.AppointmentResponse],
]:
    waiting: list[S.AppointmentResponse] = []
    checked_in: list[S.AppointmentResponse] = []
    completed: list[S.AppointmentResponse] = []
    no_show: list[S.AppointmentResponse] = []
    cancelled: list[S.AppointmentResponse] = []
    for a in items:
        row = _resp(a)
        if a.status in ("scheduled", "confirmed"):
            waiting.append(row)
        elif a.status == "checked_in":
            checked_in.append(row)
        elif a.status == "completed":
            completed.append(row)
        elif a.status == "no_show":
            no_show.append(row)
        elif a.status == "cancelled":
            cancelled.append(row)
    return waiting, checked_in, completed, no_show, cancelled


@router.post("/tenants/{tenant_id}/appointments", response_model=S.AppointmentResponse)
def create_appointment(
    tenant_id: uuid.UUID,
    body: S.AppointmentCreateRequest,
    ctx: RequestContext = Depends(require(P.APPOINTMENT_CREATE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> S.AppointmentResponse:
    match_tenant(ctx, tenant_id)
    appt = sched.create_appointment(
        db,
        tenant_id=tenant_id,
        actor_id=ctx.user_id,
        patient_id=body.patient_id,
        practitioner_id=body.practitioner_id,
        location_id=body.location_id,
        start=body.start,
        duration_minutes=body.duration_minutes,
        timezone_name=body.timezone,
        notes=body.notes,
        idempotency_key=idempotency_key or body.idempotency_key,
        location_ids=ctx.location_ids,
        walk_in=body.walk_in,
    )
    _audit(db, ctx, action="appointment.create", rid=str(appt.id))
    patient = patients_service.get_patient(db, tenant_id=tenant_id, patient_id=appt.patient_id)
    if patient.phone:
        notify_service.request_notification(
            db,
            NotifyRequest(
                channel="sms",
                to_ref=patient.phone,
                template="appointment_confirmation",
                locale="en",
                context_refs={"appointment_id": str(appt.id)},
                tenant_id=tenant_id,
            ),
        )
    return _resp(appt)


@router.get("/tenants/{tenant_id}/appointments", response_model=S.AppointmentListResponse)
def list_appointments(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.APPOINTMENT_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    practitioner_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    patient_id: uuid.UUID | None = None,
    status: str | None = None,
    start_from: datetime | None = None,
    start_to: datetime | None = None,
    limit: int = 50,
    cursor: uuid.UUID | None = None,
) -> S.AppointmentListResponse:
    match_tenant(ctx, tenant_id)
    items, next_cursor = sched.list_appointments(
        db,
        tenant_id=tenant_id,
        location_ids=ctx.location_ids,
        practitioner_id=practitioner_id,
        location_id=location_id,
        patient_id=patient_id,
        status=status,
        start_from=start_from,
        start_to=start_to,
        limit=limit,
        cursor=cursor,
    )
    return S.AppointmentListResponse(items=[_resp(a) for a in items], next_cursor=next_cursor)


@router.get(
    "/tenants/{tenant_id}/locations/{location_id}/reception-queue",
    response_model=S.ReceptionQueueResponse,
)
def reception_queue(
    tenant_id: uuid.UUID,
    location_id: uuid.UUID,
    day: date | None = None,
    practitioner_id: uuid.UUID | None = None,
    ctx: RequestContext = Depends(require(P.APPOINTMENT_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.ReceptionQueueResponse:
    match_tenant(ctx, tenant_id)
    location, queue_date, items = sched.reception_queue(
        db,
        tenant_id=tenant_id,
        location_id=location_id,
        queue_date=day,
        practitioner_id=practitioner_id,
        location_ids=ctx.location_ids,
    )
    waiting, checked_in, completed, no_show, cancelled = _bucket_queue(items)
    return S.ReceptionQueueResponse(
        location_id=location.id,
        queue_date=queue_date,
        timezone=location.timezone,
        waiting=waiting,
        checked_in=checked_in,
        completed=completed,
        no_show=no_show,
        cancelled=cancelled,
    )


@router.get("/tenants/{tenant_id}/availability", response_model=S.AvailabilityResponse)
def staff_availability(
    tenant_id: uuid.UUID,
    practitioner_id: uuid.UUID,
    location_id: uuid.UUID,
    day: date,
    ctx: RequestContext = Depends(require(P.APPOINTMENT_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.AvailabilityResponse:
    match_tenant(ctx, tenant_id)
    tz_name, slot_minutes, slots = sched.list_free_slots(
        db,
        tenant_id=tenant_id,
        practitioner_id=practitioner_id,
        location_id=location_id,
        day=day,
        location_ids=ctx.location_ids,
    )
    return S.AvailabilityResponse(
        practitioner_id=practitioner_id,
        location_id=location_id,
        timezone=tz_name,
        date=day.isoformat(),
        slot_minutes=slot_minutes,
        slots=[S.AvailabilitySlot(start_at=s, end_at=e) for s, e in slots],
    )


@router.get(
    "/tenants/{tenant_id}/appointments/{appointment_id}",
    response_model=S.AppointmentResponse,
)
def get_appointment(
    tenant_id: uuid.UUID,
    appointment_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.APPOINTMENT_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.AppointmentResponse:
    match_tenant(ctx, tenant_id)
    return _resp(sched.get_appointment(db, tenant_id=tenant_id, appointment_id=appointment_id))


@router.patch(
    "/tenants/{tenant_id}/appointments/{appointment_id}",
    response_model=S.AppointmentResponse,
)
def reschedule_appointment(
    tenant_id: uuid.UUID,
    appointment_id: uuid.UUID,
    body: S.AppointmentRescheduleRequest,
    ctx: RequestContext = Depends(require(P.APPOINTMENT_UPDATE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.AppointmentResponse:
    match_tenant(ctx, tenant_id)
    appt = sched.reschedule_appointment(
        db,
        tenant_id=tenant_id,
        appointment_id=appointment_id,
        start=body.start,
        duration_minutes=body.duration_minutes,
        location_ids=ctx.location_ids,
    )
    _audit(db, ctx, action="appointment.reschedule", rid=str(appt.id))
    return _resp(appt)


@router.post(
    "/tenants/{tenant_id}/appointments/{appointment_id}/status",
    response_model=S.AppointmentResponse,
)
def transition_appointment(
    tenant_id: uuid.UUID,
    appointment_id: uuid.UUID,
    body: S.AppointmentStatusRequest,
    ctx: RequestContext = Depends(require(P.APPOINTMENT_UPDATE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.AppointmentResponse:
    match_tenant(ctx, tenant_id)
    appt = sched.transition_appointment(
        db,
        tenant_id=tenant_id,
        appointment_id=appointment_id,
        to_status=body.status,
        location_ids=ctx.location_ids,
    )
    _audit(db, ctx, action="appointment.status", rid=str(appt.id))
    return _resp(appt)


@router.post(
    "/tenants/{tenant_id}/appointments/{appointment_id}/cancel",
    response_model=S.AppointmentResponse,
)
def cancel_appointment(
    tenant_id: uuid.UUID,
    appointment_id: uuid.UUID,
    body: S.AppointmentCancelRequest,
    ctx: RequestContext = Depends(require(P.APPOINTMENT_UPDATE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.AppointmentResponse:
    match_tenant(ctx, tenant_id)
    appt = sched.cancel_appointment(
        db,
        tenant_id=tenant_id,
        appointment_id=appointment_id,
        actor_id=ctx.user_id,
        reason=body.reason,
        location_ids=ctx.location_ids,
    )
    _audit(db, ctx, action="appointment.cancel", rid=str(appt.id))
    return _resp(appt)
