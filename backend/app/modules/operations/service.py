"""Operations dashboard aggregation. Read-only composition of existing domains.

Date semantics:
- Appointment / reception / payments / clinic hours / **ops follow-up KPIs**
  use the **location IANA timezone service day** (same as
  ``scheduling.reception_queue``).
- The follow-ups *workspace* list buckets remain UTC calendar day
  (unchanged). Ops KPIs call ``count_follow_ups_for_interval`` with the
  location service-day window instead.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.modules.billing import invoices as invoices_svc
from app.modules.clinical.models import ENCOUNTER_OPEN, Encounter
from app.modules.clinics.models import LocationWorkingHours
from app.modules.communications import service as comms_service
from app.modules.identity.models import Practitioner
from app.modules.patients.models import Patient
from app.modules.scheduling import models as sched_m
from app.modules.scheduling import service as sched_service
from app.modules.scheduling.models import Appointment
from app.modules.staff.models import StaffSchedule
from app.modules.tenancy.models import Membership, Verification
from app.platform.authz.permissions import P
from app.platform.errors import ValidationError
from app.platform.time import UTC, now

# Bounded detail table for the dashboard UI. Metrics use complete COUNTs.
APPOINTMENT_DETAIL_LIMIT = 50


def _parse_day(raw: str | None) -> date | None:
    if raw is None or raw == "":
        return None
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise ValidationError("day must be YYYY-MM-DD") from exc
    # Reject unreasonable historical/future ranges (±2 years).
    today = now().date()
    if abs((parsed - today).days) > 730:
        raise ValidationError("day is outside the supported range")
    return parsed


def _appointment_status_counts(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID,
    start_utc: datetime,
    end_utc: datetime,
    practitioner_id: uuid.UUID | None = None,
) -> dict[str, int]:
    """Complete per-status COUNTs for the location service day (no row cap)."""
    stmt = (
        select(Appointment.status, func.count())
        .where(
            Appointment.tenant_id == tenant_id,
            Appointment.location_id == location_id,
            Appointment.start_at >= start_utc,
            Appointment.start_at < end_utc,
        )
        .group_by(Appointment.status)
    )
    if practitioner_id is not None:
        stmt = stmt.where(Appointment.practitioner_id == practitioner_id)
    by_status = {str(status): int(n) for status, n in db.execute(stmt).all()}
    waiting = by_status.get(sched_m.STATUS_SCHEDULED, 0) + by_status.get(
        sched_m.STATUS_CONFIRMED, 0
    )
    return {
        "scheduled_today": sum(by_status.values()),
        "waiting": waiting,
        "checked_in": by_status.get(sched_m.STATUS_CHECKED_IN, 0),
        "completed": by_status.get(sched_m.STATUS_COMPLETED, 0),
        "cancelled": by_status.get(sched_m.STATUS_CANCELLED, 0),
        "no_show": by_status.get(sched_m.STATUS_NO_SHOW, 0),
    }


def _detail_list_total(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID,
    start_utc: datetime,
    end_utc: datetime,
    practitioner_id: uuid.UUID | None,
    status: str | None,
    buckets: dict[str, int],
) -> int:
    """Complete COUNT for the detail list filter (independent of row cap)."""
    if status is None:
        return int(buckets["scheduled_today"])
    status_key = {
        sched_m.STATUS_CHECKED_IN: "checked_in",
        sched_m.STATUS_COMPLETED: "completed",
        sched_m.STATUS_CANCELLED: "cancelled",
        sched_m.STATUS_NO_SHOW: "no_show",
    }.get(status)
    if status_key is not None:
        return int(buckets[status_key])
    stmt = (
        select(func.count())
        .select_from(Appointment)
        .where(
            Appointment.tenant_id == tenant_id,
            Appointment.location_id == location_id,
            Appointment.start_at >= start_utc,
            Appointment.start_at < end_utc,
            Appointment.status == status,
        )
    )
    if practitioner_id is not None:
        stmt = stmt.where(Appointment.practitioner_id == practitioner_id)
    return int(db.execute(stmt).scalar_one())


def _open_encounters(
    db: DBSession, *, tenant_id: uuid.UUID, location_id: uuid.UUID
) -> int:
    return int(
        db.execute(
            select(func.count())
            .select_from(Encounter)
            .where(
                Encounter.tenant_id == tenant_id,
                Encounter.location_id == location_id,
                Encounter.status == ENCOUNTER_OPEN,
            )
        ).scalar_one()
    )


def _follow_up_counts(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None,
    start_utc: datetime,
    end_utc: datetime,
) -> dict[str, int]:
    """Location service-day follow-up KPIs (complete COUNTs, no list cap)."""
    return comms_service.count_follow_ups_for_interval(
        db,
        tenant_id=tenant_id,
        location_id=location_id,
        start_utc=start_utc,
        end_utc=end_utc,
        location_ids=location_ids,
    )


def _billing_metrics(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID,
    start_utc: datetime,
    end_utc: datetime,
) -> dict[str, object]:
    """Complete location AR + payments (SQL aggregates, no row cap)."""
    count, outstanding = invoices_svc.location_outstanding_summary(
        db, tenant_id=tenant_id, location_id=location_id
    )
    pay_count, pay_total = invoices_svc.location_payments_in_interval(
        db,
        tenant_id=tenant_id,
        location_id=location_id,
        start_utc=start_utc,
        end_utc=end_utc,
    )
    return {
        "outstanding_invoice_count": count,
        "outstanding_amount": f"{outstanding}",
        "currency": "INR",
        "payments_today_count": pay_count,
        "payments_today_amount": f"{pay_total}",
    }


def _appointment_rows(
    db: DBSession, items: list[Appointment]
) -> list[dict[str, object]]:
    if not items:
        return []
    patient_ids = {a.patient_id for a in items}
    pract_ids = {a.practitioner_id for a in items}
    patients = {
        p.id: p
        for p in db.execute(select(Patient).where(Patient.id.in_(list(patient_ids)))).scalars()
    }
    practs = {
        p.id: p
        for p in db.execute(
            select(Practitioner).where(Practitioner.id.in_(list(pract_ids)))
        ).scalars()
    }
    rows: list[dict[str, object]] = []
    for a in items:
        pat = patients.get(a.patient_id)
        pr = practs.get(a.practitioner_id)
        # Dashboard shows identity only — no clinical notes content beyond
        # the short appointment reason field already on the appointment.
        rows.append(
            {
                "id": a.id,
                "start_at": a.start_at,
                "end_at": a.end_at,
                "status": a.status,
                "patient_id": a.patient_id,
                "patient_display_name": pat.display_name if pat else "Unknown",
                "practitioner_id": a.practitioner_id,
                "practitioner_display_name": pr.display_name if pr else "Unknown",
                "location_id": a.location_id,
                "queue_token": a.queue_token,
                "notes": a.notes,
            }
        )
    return rows


def _availability(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID,
    service_date: date,
    include_staff_schedules: bool,
) -> dict[str, object]:
    hours = list(
        db.execute(
            select(LocationWorkingHours).where(
                LocationWorkingHours.tenant_id == tenant_id,
                LocationWorkingHours.location_id == location_id,
                LocationWorkingHours.weekday == service_date.weekday(),
            )
        ).scalars()
    )
    clinic_hours = [
        {"start_local": h.start_local, "end_local": h.end_local} for h in hours
    ]

    verifications = list(
        db.execute(
            select(Verification, Practitioner)
            .join(Practitioner, Verification.practitioner_id == Practitioner.id)
            .where(
                Verification.tenant_id == tenant_id,
                Verification.status == "approved",
                Practitioner.is_active.is_(True),
            )
            .order_by(Practitioner.display_name)
        ).all()
    )

    schedule_by_user: dict[uuid.UUID, list[str]] = {}
    if include_staff_schedules:
        weekday = service_date.weekday()
        sched_rows = list(
            db.execute(
                select(StaffSchedule, Membership)
                .join(Membership, StaffSchedule.membership_id == Membership.id)
                .where(
                    StaffSchedule.tenant_id == tenant_id,
                    StaffSchedule.location_id == location_id,
                    StaffSchedule.weekday == weekday,
                    StaffSchedule.is_active.is_(True),
                    StaffSchedule.effective_from <= service_date,
                    (StaffSchedule.effective_to.is_(None))
                    | (StaffSchedule.effective_to >= service_date),
                )
            ).all()
        )
        for sch, mem in sched_rows:
            label = (
                f"{sch.start_time.strftime('%H:%M')}-{sch.end_time.strftime('%H:%M')}"
            )
            schedule_by_user.setdefault(mem.user_id, []).append(label)

    practitioners: list[dict[str, object]] = []
    for ver, pract in verifications:
        windows: list[str] = []
        if pract.user_id and pract.user_id in schedule_by_user:
            windows = schedule_by_user[pract.user_id]
        practitioners.append(
            {
                "practitioner_id": pract.id,
                "display_name": pract.display_name,
                "verification_status": ver.status,
                "staff_windows": windows,
            }
        )
    return {"clinic_hours": clinic_hours, "practitioners": practitioners}


def build_operations_dashboard(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID,
    permissions: frozenset[str],
    location_ids: frozenset[uuid.UUID] | None,
    day: str | None = None,
    practitioner_id: uuid.UUID | None = None,
    status: str | None = None,
) -> dict[str, object]:
    """Compose the dashboard. Sections omitted when the actor lacks permission."""
    parsed_day = _parse_day(day)
    # Validate location scope via reception_queue path.
    location, service_date, _items = sched_service.reception_queue(
        db,
        tenant_id=tenant_id,
        location_id=location_id,
        queue_date=parsed_day,
        practitioner_id=practitioner_id,
        location_ids=location_ids,
    )
    tz = sched_service.resolve_timezone(None, location_timezone=location.timezone)
    start_local = datetime.combine(service_date, datetime.min.time()).replace(tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(UTC)
    end_utc = end_local.astimezone(UTC)

    omitted: list[str] = []
    appointments_metrics = None
    reception_metrics = None
    follow_ups = None
    billing = None
    availability = None
    todays: list[dict[str, object]] = []
    list_meta: dict[str, object] | None = None
    follow_up_day_basis: str | None = None

    if P.APPOINTMENT_READ in permissions:
        buckets = _appointment_status_counts(
            db,
            tenant_id=tenant_id,
            location_id=location_id,
            start_utc=start_utc,
            end_utc=end_utc,
            practitioner_id=practitioner_id,
        )
        in_consult = _open_encounters(db, tenant_id=tenant_id, location_id=location_id)
        metrics = {**buckets, "in_consultation": in_consult}
        appointments_metrics = metrics
        reception_metrics = metrics
        # Dedicated bounded query — do not slice the reception 200-cap list.
        detail_q = (
            select(Appointment)
            .where(
                Appointment.tenant_id == tenant_id,
                Appointment.location_id == location_id,
                Appointment.start_at >= start_utc,
                Appointment.start_at < end_utc,
            )
            .order_by(Appointment.start_at, Appointment.id)
            .limit(APPOINTMENT_DETAIL_LIMIT)
        )
        if practitioner_id is not None:
            detail_q = detail_q.where(Appointment.practitioner_id == practitioner_id)
        if status:
            detail_q = detail_q.where(Appointment.status == status)
        detail = list(db.execute(detail_q).scalars().all())
        todays = _appointment_rows(db, detail)
        total_for_filter = _detail_list_total(
            db,
            tenant_id=tenant_id,
            location_id=location_id,
            start_utc=start_utc,
            end_utc=end_utc,
            practitioner_id=practitioner_id,
            status=status,
            buckets=buckets,
        )
        list_meta = {
            "total": total_for_filter,
            "returned": len(todays),
            "truncated": total_for_filter > len(todays),
            "limit": APPOINTMENT_DETAIL_LIMIT,
        }
    else:
        omitted.append("appointments")
        omitted.append("reception")

    if P.FOLLOWUP_READ in permissions:
        follow_ups = _follow_up_counts(
            db,
            tenant_id=tenant_id,
            location_id=location_id,
            location_ids=location_ids,
            start_utc=start_utc,
            end_utc=end_utc,
        )
        follow_up_day_basis = "location_service_day"
    else:
        omitted.append("follow_ups")

    if P.BILLING_READ in permissions:
        billing = _billing_metrics(
            db,
            tenant_id=tenant_id,
            location_id=location_id,
            start_utc=start_utc,
            end_utc=end_utc,
        )
    else:
        omitted.append("billing")

    if P.APPOINTMENT_READ in permissions or P.STAFF_MANAGE in permissions:
        availability = _availability(
            db,
            tenant_id=tenant_id,
            location_id=location_id,
            service_date=service_date,
            include_staff_schedules=P.STAFF_MANAGE in permissions,
        )
    else:
        omitted.append("availability")

    return {
        "tenant_id": tenant_id,
        "location_id": location.id,
        "location_name": location.name,
        "service_date": service_date,
        "timezone": location.timezone,
        "appointments": appointments_metrics,
        "reception": reception_metrics,
        "follow_ups": follow_ups,
        "billing": billing,
        "availability": availability,
        "todays_appointments": todays,
        "appointments_list": list_meta,
        "sections_omitted": omitted,
        "follow_up_day_basis": follow_up_day_basis,
    }
