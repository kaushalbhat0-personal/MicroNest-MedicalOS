"""Scheduling service. Single source of truth for:

- appointment lifecycle transitions (`TRANSITIONS` + `transition`)
- wall-clock interpretation (`resolve_interval`)
- double-booking protection (transaction-scoped advisory lock + overlap query)
- tenant / location scope enforcement on every read and write

Routers translate the RequestContext into explicit arguments; they never
implement these rules themselves.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import text
from sqlalchemy.orm import Session as DBSession

from app.modules.clinics import service as clinics_service
from app.modules.clinics.models import Location
from app.modules.identity.models import Practitioner
from app.modules.patients import service as patients_service
from app.modules.patients.models import Patient
from app.modules.scheduling import models as M
from app.modules.scheduling.models import Appointment
from app.modules.tenancy import service as tenancy_service
from app.platform import ids
from app.platform.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.platform.time import UTC

# --- Lifecycle: the ONE transition table. `transition()` is the only writer. ---

TRANSITIONS: dict[str, frozenset[str]] = {
    M.STATUS_SCHEDULED: frozenset(
        {M.STATUS_CONFIRMED, M.STATUS_CHECKED_IN, M.STATUS_CANCELLED, M.STATUS_NO_SHOW}
    ),
    M.STATUS_CONFIRMED: frozenset({M.STATUS_CHECKED_IN, M.STATUS_CANCELLED, M.STATUS_NO_SHOW}),
    M.STATUS_CHECKED_IN: frozenset({M.STATUS_COMPLETED, M.STATUS_CANCELLED}),
    M.STATUS_COMPLETED: frozenset(),
    M.STATUS_CANCELLED: frozenset(),
    M.STATUS_NO_SHOW: frozenset(),
}

# Overlap only matters for live bookings; history never blocks the future.
LIVE_STATUSES = (M.STATUS_SCHEDULED, M.STATUS_CONFIRMED, M.STATUS_CHECKED_IN)

MIN_DURATION_MINUTES = 5
MAX_DURATION_MINUTES = 480


def _now() -> datetime:
    return datetime.now(UTC)


# --- Timezone interpretation (single source) ---


def resolve_timezone(name: str | None, *, location_timezone: str) -> ZoneInfo:
    """IANA zone for wall-clock input. Explicit request value wins, otherwise
    the location's zone. Unknown names are 422, never server-local fallback."""
    candidate = (name or "").strip() or location_timezone
    try:
        return ZoneInfo(candidate)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValidationError(f"unknown timezone: {candidate}") from exc


def resolve_interval(
    start: datetime,
    duration_minutes: int,
    *,
    tz: ZoneInfo,
    now: datetime,
    enforce_future: bool = True,
) -> tuple[datetime, datetime]:
    """Wall-clock/aware input -> UTC (start, end) instants.

    - Aware datetimes are instants already (any offset accepted).
    - Naive datetimes are wall-clock in `tz` (fold=0 for ambiguous DST times).
    - Non-existent DST-gap wall times are rejected (round-trip check).
    - Start must be in the future; duration is bounded by the API schema.
    """
    if not (MIN_DURATION_MINUTES <= duration_minutes <= MAX_DURATION_MINUTES):
        raise ValidationError("duration_minutes must be between 5 and 480")
    if start.tzinfo is None:
        wall = start.replace(second=0, microsecond=0)
        instant = wall.replace(tzinfo=tz, fold=0).astimezone(UTC)
        if instant.astimezone(tz).replace(tzinfo=None) != wall:
            raise ValidationError("start time does not exist in the given timezone (DST gap)")
    else:
        instant = start.astimezone(UTC)
    if instant <= now and enforce_future:
        raise ValidationError("start must be in the future")
    return instant, instant + timedelta(minutes=duration_minutes)


# --- Concurrency: advisory lock + overlap query ---


def _lock_practitioner(db: DBSession, practitioner_id: uuid.UUID) -> None:
    """Serialize booking decisions per practitioner for this transaction.

    btree_gist is not guaranteed on every deployment target (managed,
    private, on-prem), so range-exclusion constraints are not portable here.
    The transaction-scoped advisory lock makes check-then-insert atomic per
    practitioner under READ COMMITTED; concurrent conflicting writers block
    on the lock, then see the winner's row and fail closed with 409.
    """
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key)::bigint)"),
        {"key": f"sched:{practitioner_id}"},
    )


def _overlap_exists(
    db: DBSession,
    *,
    practitioner_id: uuid.UUID,
    start_at: datetime,
    end_at: datetime,
    exclude_id: uuid.UUID | None = None,
) -> bool:
    # IN-list derived from LIVE_STATUSES (module constants, never user input).
    live = ", ".join(f"'{s}'" for s in sorted(LIVE_STATUSES))
    q = (
        "SELECT 1 FROM appointments "  # noqa: S608 — IN-list is LIVE_STATUSES constants only
        "WHERE practitioner_id = :p "
        f"AND status IN ({live}) "
        "AND tstzrange(start_at, end_at) && tstzrange(:s, :e) "
    )
    params: dict[str, object] = {"p": str(practitioner_id), "s": start_at, "e": end_at}
    if exclude_id is not None:
        q += "AND id != :x "
        params["x"] = str(exclude_id)
    q += "LIMIT 1"
    return db.execute(text(q), params).first() is not None


def assert_slot_free(
    db: DBSession,
    *,
    practitioner_id: uuid.UUID,
    start_at: datetime,
    end_at: datetime,
    exclude_id: uuid.UUID | None = None,
) -> None:
    """Availability seam: no live overlap for this practitioner. Deterministic;
    shift/rota intelligence is explicitly deferred (no rostering in P2)."""
    if _overlap_exists(
        db,
        practitioner_id=practitioner_id,
        start_at=start_at,
        end_at=end_at,
        exclude_id=exclude_id,
    ):
        raise ConflictError("practitioner is already booked for this time")


# --- Scope + reference validation ---


def _check_location_scope(
    location_ids: frozenset[uuid.UUID] | None, location_id: uuid.UUID
) -> None:
    if location_ids and location_id not in location_ids:
        raise ForbiddenError("location is outside your scope")


def _validated_refs(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    practitioner_id: uuid.UUID,
    location_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None,
) -> tuple[Patient, Practitioner, Location]:
    patient = patients_service.get_patient(db, tenant_id=tenant_id, patient_id=patient_id)
    if not patient.is_active:
        raise ValidationError("patient is not active")
    practitioner = db.get(Practitioner, practitioner_id)
    if practitioner is None or not practitioner.is_active:
        raise NotFoundError("practitioner not found")
    if not tenancy_service.is_practitioner_verified(
        db, tenant_id=tenant_id, practitioner_id=practitioner_id
    ):
        raise ForbiddenError("practitioner is not verified for this tenant")
    location = clinics_service.get_location(db, tenant_id=tenant_id, location_id=location_id)
    if not location.is_active:
        raise ValidationError("location is not active")
    _check_location_scope(location_ids, location_id)
    return patient, practitioner, location


# --- Commands ---


def create_appointment(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    patient_id: uuid.UUID,
    practitioner_id: uuid.UUID,
    location_id: uuid.UUID,
    start: datetime,
    duration_minutes: int,
    timezone_name: str | None = None,
    notes: str | None = None,
    idempotency_key: str | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Appointment:
    now = _now()
    if idempotency_key:
        existing = db.execute(
            text(
                "SELECT id FROM appointments "
                "WHERE tenant_id = :t AND idempotency_key = :k LIMIT 1"
            ),
            {"t": str(tenant_id), "k": idempotency_key},
        ).first()
        if existing is not None:
            found = get_appointment(db, tenant_id=tenant_id, appointment_id=existing[0])
            # Same key must mean the same booking intent; anything else is
            # a key reuse across different bookings and fails closed.
            location = clinics_service.get_location(
                db, tenant_id=tenant_id, location_id=location_id
            )
            tz = resolve_timezone(timezone_name, location_timezone=location.timezone)
            start_at, end_at = resolve_interval(
                start, duration_minutes, tz=tz, now=now, enforce_future=False
            )
            if (
                found.patient_id != patient_id
                or found.practitioner_id != practitioner_id
                or found.location_id != location_id
                or found.start_at != start_at
                or found.end_at != end_at
            ):
                raise ConflictError("idempotency key was used for a different booking")
            return found
    _lock_practitioner(db, practitioner_id)
    _, _, location = _validated_refs(
        db,
        tenant_id=tenant_id,
        patient_id=patient_id,
        practitioner_id=practitioner_id,
        location_id=location_id,
        location_ids=location_ids,
    )
    tz = resolve_timezone(timezone_name, location_timezone=location.timezone)
    start_at, end_at = resolve_interval(start, duration_minutes, tz=tz, now=now)
    assert_slot_free(db, practitioner_id=practitioner_id, start_at=start_at, end_at=end_at)
    note = (notes or "").strip() or None
    appt = Appointment(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        patient_id=patient_id,
        practitioner_id=practitioner_id,
        location_id=location_id,
        start_at=start_at,
        end_at=end_at,
        timezone=str(tz.key),
        status=M.STATUS_SCHEDULED,
        notes=note,
        idempotency_key=idempotency_key or None,
        created_by=actor_id,
        created_at=now,
        updated_at=now,
    )
    db.add(appt)
    db.flush()
    return appt


def get_appointment(
    db: DBSession, *, tenant_id: uuid.UUID, appointment_id: uuid.UUID
) -> Appointment:
    appt = db.get(Appointment, appointment_id)
    if appt is None or appt.tenant_id != tenant_id:
        raise NotFoundError("appointment not found")
    return appt


def list_appointments(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
    practitioner_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    status: str | None = None,
    start_from: datetime | None = None,
    start_to: datetime | None = None,
    limit: int = 50,
    cursor: uuid.UUID | None = None,
) -> tuple[list[Appointment], uuid.UUID | None]:
    """Keyset page over (start_at, id). Returns (items, next_cursor|None)."""
    from sqlalchemy import select

    if location_id is not None:
        _check_location_scope(location_ids, location_id)
    q = select(Appointment).where(Appointment.tenant_id == tenant_id)
    if location_ids:
        q = q.where(Appointment.location_id.in_(list(location_ids)))
    if practitioner_id is not None:
        q = q.where(Appointment.practitioner_id == practitioner_id)
    if location_id is not None:
        q = q.where(Appointment.location_id == location_id)
    if status is not None:
        if status not in M.STATUSES:
            raise ValidationError("unknown status")
        q = q.where(Appointment.status == status)
    if start_from is not None:
        aware = start_from if start_from.tzinfo else start_from.replace(tzinfo=UTC)
        q = q.where(Appointment.start_at >= aware)
    if start_to is not None:
        aware = start_to if start_to.tzinfo else start_to.replace(tzinfo=UTC)
        q = q.where(Appointment.start_at < aware)
    if cursor is not None:
        anchor = get_appointment(db, tenant_id=tenant_id, appointment_id=cursor)
        q = q.where(
            (Appointment.start_at > anchor.start_at)
            | ((Appointment.start_at == anchor.start_at) & (Appointment.id > anchor.id))
        )
    q = q.order_by(Appointment.start_at, Appointment.id).limit(min(max(limit, 1), 200) + 1)
    rows = list(db.execute(q).scalars().all())
    if len(rows) > min(max(limit, 1), 200):
        return rows[:-1], rows[-2].id
    return rows, None


def reschedule_appointment(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    appointment_id: uuid.UUID,
    start: datetime,
    duration_minutes: int,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Appointment:
    appt = get_appointment(db, tenant_id=tenant_id, appointment_id=appointment_id)
    _check_location_scope(location_ids, appt.location_id)
    if appt.status not in (M.STATUS_SCHEDULED, M.STATUS_CONFIRMED):
        raise ValidationError("only scheduled or confirmed appointments can be rescheduled")
    _lock_practitioner(db, appt.practitioner_id)
    location = clinics_service.get_location(db, tenant_id=tenant_id, location_id=appt.location_id)
    tz = resolve_timezone(None, location_timezone=location.timezone)
    start_at, end_at = resolve_interval(start, duration_minutes, tz=tz, now=_now())
    assert_slot_free(
        db,
        practitioner_id=appt.practitioner_id,
        start_at=start_at,
        end_at=end_at,
        exclude_id=appt.id,
    )
    appt.start_at = start_at
    appt.end_at = end_at
    appt.updated_at = _now()
    db.flush()
    return appt


def transition_appointment(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    appointment_id: uuid.UUID,
    to_status: str,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Appointment:
    """The ONLY status writer. Same-state requests are no-op successes so
    client retries are idempotent; anything else outside TRANSITIONS is 422."""
    if to_status not in M.STATUSES:
        raise ValidationError("unknown status")
    appt = get_appointment(db, tenant_id=tenant_id, appointment_id=appointment_id)
    _check_location_scope(location_ids, appt.location_id)
    if appt.status == to_status:
        return appt
    if to_status not in TRANSITIONS[appt.status]:
        raise ValidationError(f"cannot move appointment from {appt.status} to {to_status}")
    appt.status = to_status
    appt.updated_at = _now()
    db.flush()
    return appt


def cancel_appointment(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    appointment_id: uuid.UUID,
    actor_id: uuid.UUID,
    reason: str | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Appointment:
    appt = transition_appointment(
        db,
        tenant_id=tenant_id,
        appointment_id=appointment_id,
        to_status=M.STATUS_CANCELLED,
        location_ids=location_ids,
    )
    now = _now()
    if appt.cancelled_at is None:
        appt.cancelled_at = now
        appt.cancelled_by = actor_id
    if reason is not None:
        cleaned = reason.strip()
        if len(cleaned) > 200:
            raise ValidationError("cancel reason must be at most 200 characters")
        appt.cancel_reason = cleaned or None
    appt.updated_at = now
    db.flush()
    return appt
