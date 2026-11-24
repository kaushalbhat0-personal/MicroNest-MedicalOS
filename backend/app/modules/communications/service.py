"""Follow-ups, communication consent, and communication logs."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as DBSession

from app.modules.clinics import service as clinics_service
from app.modules.communications import models as M
from app.modules.communications.models import (
    CommunicationConsent,
    CommunicationLog,
    FollowUp,
)
from app.modules.patients import service as patients_service
from app.platform import ids
from app.platform.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.platform.time import UTC, as_utc, now

TRANSITIONS: dict[str, frozenset[str]] = {
    M.FU_OPEN: frozenset({M.FU_IN_PROGRESS, M.FU_SNOOZED, M.FU_COMPLETED, M.FU_CANCELLED}),
    M.FU_IN_PROGRESS: frozenset({M.FU_OPEN, M.FU_SNOOZED, M.FU_COMPLETED, M.FU_CANCELLED}),
    M.FU_SNOOZED: frozenset({M.FU_OPEN, M.FU_IN_PROGRESS, M.FU_COMPLETED, M.FU_CANCELLED}),
    M.FU_COMPLETED: frozenset(),
    M.FU_CANCELLED: frozenset(),
}


def _check_location(
    location_ids: frozenset[uuid.UUID] | None, location_id: uuid.UUID
) -> None:
    if location_ids and location_id not in location_ids:
        raise ForbiddenError("location is outside your scope")


def create_follow_up(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    patient_id: uuid.UUID,
    location_id: uuid.UUID,
    due_at: datetime,
    category: str,
    reason: str,
    source_type: str = M.FU_SRC_MANUAL,
    source_id: uuid.UUID | None = None,
    priority: str = M.FU_PRI_NORMAL,
    assigned_user_id: uuid.UUID | None = None,
    next_action: str | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> FollowUp:
    if category not in M.FOLLOWUP_CATEGORIES:
        raise ValidationError("unknown follow-up category")
    if source_type not in M.FOLLOWUP_SOURCE_TYPES:
        raise ValidationError("unknown source type")
    if priority not in M.FOLLOWUP_PRIORITIES:
        raise ValidationError("unknown priority")
    cleaned = (reason or "").strip()
    if len(cleaned) < 2 or len(cleaned) > 200:
        raise ValidationError("reason must be 2-200 characters")
    if source_type != M.FU_SRC_MANUAL and source_id is None:
        raise ValidationError("source_id required for non-manual follow-ups")
    if source_type == M.FU_SRC_MANUAL:
        source_id = None

    patients_service.get_patient(db, tenant_id=tenant_id, patient_id=patient_id)
    clinics_service.get_location(db, tenant_id=tenant_id, location_id=location_id)
    _check_location(location_ids, location_id)

    due = as_utc(due_at)
    if due.tzinfo is None:
        due = due.replace(tzinfo=UTC)

    if source_id is not None:
        existing = db.execute(
            select(FollowUp).where(
                FollowUp.tenant_id == tenant_id,
                FollowUp.source_type == source_type,
                FollowUp.source_id == source_id,
                FollowUp.category == category,
                FollowUp.status.in_(list(M.FOLLOWUP_ACTIVE)),
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ConflictError("an active follow-up already exists for this source")

    ts = now()
    row = FollowUp(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        patient_id=patient_id,
        location_id=location_id,
        assigned_user_id=assigned_user_id,
        due_at=due,
        category=category,
        reason=cleaned,
        source_type=source_type,
        source_id=source_id,
        priority=priority,
        status=M.FU_OPEN,
        next_action=(next_action or "").strip() or None,
        created_by=actor_id,
        created_at=ts,
        updated_at=ts,
    )
    db.add(row)
    db.flush()
    return row


def get_follow_up(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    follow_up_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> FollowUp:
    row = db.get(FollowUp, follow_up_id)
    if row is None or row.tenant_id != tenant_id:
        raise NotFoundError("follow-up not found")
    _check_location(location_ids, row.location_id)
    return row


def list_follow_ups(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
    patient_id: uuid.UUID | None = None,
    assigned_user_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    status: str | None = None,
    category: str | None = None,
    priority: str | None = None,
    bucket: str | None = None,
    due_from: datetime | None = None,
    due_to: datetime | None = None,
    limit: int = 50,
) -> list[FollowUp]:
    """List follow-ups. ``bucket`` is a derived view filter, not a stored status:
    due_today | overdue | upcoming | in_progress | completed | assigned_to_me | all.
    """
    q = select(FollowUp).where(FollowUp.tenant_id == tenant_id)
    if location_ids:
        q = q.where(FollowUp.location_id.in_(list(location_ids)))
    if patient_id is not None:
        q = q.where(FollowUp.patient_id == patient_id)
    if assigned_user_id is not None:
        q = q.where(FollowUp.assigned_user_id == assigned_user_id)
    if location_id is not None:
        _check_location(location_ids, location_id)
        q = q.where(FollowUp.location_id == location_id)
    if status is not None:
        if status not in M.FOLLOWUP_STATUSES:
            raise ValidationError("unknown status")
        q = q.where(FollowUp.status == status)
    if category is not None:
        if category not in M.FOLLOWUP_CATEGORIES:
            raise ValidationError("unknown category")
        q = q.where(FollowUp.category == category)
    if priority is not None:
        if priority not in M.FOLLOWUP_PRIORITIES:
            raise ValidationError("unknown priority")
        q = q.where(FollowUp.priority == priority)
    if due_from is not None:
        q = q.where(FollowUp.due_at >= as_utc(due_from))
    if due_to is not None:
        q = q.where(FollowUp.due_at < as_utc(due_to))

    current = now()
    start_today = current.replace(hour=0, minute=0, second=0, microsecond=0)
    end_today = start_today + timedelta(days=1)

    if bucket == "due_today":
        q = q.where(
            FollowUp.status.in_([M.FU_OPEN, M.FU_IN_PROGRESS]),
            FollowUp.due_at >= start_today,
            FollowUp.due_at < end_today,
        )
    elif bucket == "overdue":
        q = q.where(
            FollowUp.status.in_([M.FU_OPEN, M.FU_IN_PROGRESS]),
            FollowUp.due_at < start_today,
        )
    elif bucket == "upcoming":
        q = q.where(
            FollowUp.status.in_([M.FU_OPEN, M.FU_IN_PROGRESS, M.FU_SNOOZED]),
            FollowUp.due_at >= end_today,
        )
    elif bucket == "in_progress":
        q = q.where(FollowUp.status == M.FU_IN_PROGRESS)
    elif bucket == "completed":
        q = q.where(FollowUp.status == M.FU_COMPLETED)
    elif bucket == "assigned_to_me":
        # Caller must pass assigned_user_id; without it this is empty.
        if assigned_user_id is None:
            return []
        q = q.where(
            FollowUp.assigned_user_id == assigned_user_id,
            FollowUp.status.in_(list(M.FOLLOWUP_ACTIVE)),
        )
    elif bucket in (None, "all"):
        pass
    else:
        raise ValidationError("unknown bucket")

    capped = min(max(limit, 1), 200)
    return list(db.execute(q.order_by(FollowUp.due_at, FollowUp.id).limit(capped)).scalars().all())


def count_follow_ups_for_interval(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID,
    start_utc: datetime,
    end_utc: datetime,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> dict[str, int]:
    """COUNT follow-ups against an explicit [start_utc, end_utc) window.

    Used by the operations dashboard for **location service-day** KPIs.
    Does not change ``list_follow_ups`` UTC bucket semantics used by the
    follow-ups workspace.

    Boundaries (due_at is timestamptz; compared as UTC instants):
    - due_today: status in {open, in_progress}, start <= due_at < end
    - overdue: status in {open, in_progress}, due_at < start
    - upcoming: status in {open, in_progress, snoozed}, due_at >= end
    Completed and cancelled are excluded from all three.
    Snoozed is excluded from due_today/overdue (matches workspace buckets).
    """
    _check_location(location_ids, location_id)
    start = as_utc(start_utc)
    end = as_utc(end_utc)
    if end <= start:
        raise ValidationError("end_utc must be after start_utc")

    base = [
        FollowUp.tenant_id == tenant_id,
        FollowUp.location_id == location_id,
    ]

    due_today = int(
        db.execute(
            select(func.count())
            .select_from(FollowUp)
            .where(
                *base,
                FollowUp.status.in_([M.FU_OPEN, M.FU_IN_PROGRESS]),
                FollowUp.due_at >= start,
                FollowUp.due_at < end,
            )
        ).scalar_one()
    )
    overdue = int(
        db.execute(
            select(func.count())
            .select_from(FollowUp)
            .where(
                *base,
                FollowUp.status.in_([M.FU_OPEN, M.FU_IN_PROGRESS]),
                FollowUp.due_at < start,
            )
        ).scalar_one()
    )
    upcoming = int(
        db.execute(
            select(func.count())
            .select_from(FollowUp)
            .where(
                *base,
                FollowUp.status.in_([M.FU_OPEN, M.FU_IN_PROGRESS, M.FU_SNOOZED]),
                FollowUp.due_at >= end,
            )
        ).scalar_one()
    )
    return {"due_today": due_today, "overdue": overdue, "upcoming": upcoming}


def transition_follow_up(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    follow_up_id: uuid.UUID,
    actor_id: uuid.UUID,
    new_status: str,
    outcome: str | None = None,
    next_action: str | None = None,
    next_due_at: datetime | None = None,
    snooze_until: datetime | None = None,
    assigned_user_id: uuid.UUID | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> FollowUp:
    row = get_follow_up(
        db, tenant_id=tenant_id, follow_up_id=follow_up_id, location_ids=location_ids
    )
    if new_status not in M.FOLLOWUP_STATUSES:
        raise ValidationError("unknown status")
    allowed = TRANSITIONS.get(row.status, frozenset())
    if new_status not in allowed:
        raise ConflictError(f"cannot transition {row.status} → {new_status}")

    if new_status == M.FU_SNOOZED:
        if snooze_until is None:
            raise ValidationError("snooze_until required")
        until = as_utc(snooze_until)
        if until <= now():
            raise ValidationError("snooze_until must be in the future")
        row.snooze_until = until
        row.due_at = until
    else:
        row.snooze_until = None

    if new_status == M.FU_COMPLETED:
        row.completed_at = now()
        row.completed_by = actor_id
        row.outcome = (outcome or "").strip() or "completed"
        if next_action is not None:
            row.next_action = next_action.strip() or None
        if next_due_at is not None:
            row.next_due_at = as_utc(next_due_at)
    if new_status == M.FU_CANCELLED:
        row.completed_at = now()
        row.completed_by = actor_id
        row.outcome = (outcome or "").strip() or "cancelled"

    if assigned_user_id is not None:
        row.assigned_user_id = assigned_user_id
    if next_action is not None and new_status != M.FU_COMPLETED:
        row.next_action = next_action.strip() or None

    row.status = new_status
    row.updated_at = now()
    db.flush()
    return row


def assign_follow_up(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    follow_up_id: uuid.UUID,
    assigned_user_id: uuid.UUID | None,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> FollowUp:
    row = get_follow_up(
        db, tenant_id=tenant_id, follow_up_id=follow_up_id, location_ids=location_ids
    )
    if row.status not in M.FOLLOWUP_ACTIVE:
        raise ConflictError("cannot assign a closed follow-up")
    row.assigned_user_id = assigned_user_id
    row.updated_at = now()
    db.flush()
    return row


# --- Consent ---


def current_consent(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    channel: str,
    purpose: str,
) -> CommunicationConsent | None:
    return db.execute(
        select(CommunicationConsent).where(
            CommunicationConsent.tenant_id == tenant_id,
            CommunicationConsent.patient_id == patient_id,
            CommunicationConsent.channel == channel,
            CommunicationConsent.purpose == purpose,
            CommunicationConsent.is_current.is_(True),
        )
    ).scalar_one_or_none()


def consent_status(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    channel: str,
    purpose: str,
) -> str:
    """Return granted | denied | revoked | unknown. Fail-closed for callers."""
    row = current_consent(
        db,
        tenant_id=tenant_id,
        patient_id=patient_id,
        channel=channel,
        purpose=purpose,
    )
    if row is None:
        return "unknown"
    return row.status


def is_channel_eligible(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    channel: str,
    purpose: str,
) -> bool:
    """True only when an explicit granted current consent exists for this pair."""
    return (
        consent_status(
            db,
            tenant_id=tenant_id,
            patient_id=patient_id,
            channel=channel,
            purpose=purpose,
        )
        == M.CC_GRANTED
    )


def record_consent(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    patient_id: uuid.UUID,
    channel: str,
    purpose: str,
    status: str,
    capture_source: str = M.CAPTURE_STAFF,
) -> CommunicationConsent:
    if channel not in M.CONSENT_CHANNELS:
        raise ValidationError("unknown consent channel")
    if purpose not in M.COMM_PURPOSES:
        raise ValidationError("unknown consent purpose")
    if status not in (M.CC_GRANTED, M.CC_DENIED):
        raise ValidationError("status must be granted or denied")
    if capture_source not in M.CAPTURE_SOURCES:
        raise ValidationError("unknown capture source")

    patients_service.get_patient(db, tenant_id=tenant_id, patient_id=patient_id)
    ts = now()
    previous = current_consent(
        db,
        tenant_id=tenant_id,
        patient_id=patient_id,
        channel=channel,
        purpose=purpose,
    )
    # Clear current flag before insert so uq_comm_consent_current stays unique.
    if previous is not None:
        previous.is_current = False
        db.flush()
    row = CommunicationConsent(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        patient_id=patient_id,
        channel=channel,
        purpose=purpose,
        status=status,
        capture_source=capture_source,
        recorded_by=actor_id,
        captured_at=ts,
        is_current=True,
        created_at=ts,
    )
    db.add(row)
    db.flush()
    if previous is not None:
        previous.superseded_by_id = row.id
        db.flush()
    return row


def revoke_consent(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    patient_id: uuid.UUID,
    channel: str,
    purpose: str,
) -> CommunicationConsent:
    patients_service.get_patient(db, tenant_id=tenant_id, patient_id=patient_id)
    previous = current_consent(
        db,
        tenant_id=tenant_id,
        patient_id=patient_id,
        channel=channel,
        purpose=purpose,
    )
    if previous is None:
        raise NotFoundError("no current consent to revoke")
    if previous.status == M.CC_REVOKED:
        raise ConflictError("consent already revoked")

    ts = now()
    previous.is_current = False
    if previous.status == M.CC_GRANTED:
        previous.revoked_at = ts
        previous.revoked_by = actor_id
    db.flush()
    row = CommunicationConsent(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        patient_id=patient_id,
        channel=channel,
        purpose=purpose,
        status=M.CC_REVOKED,
        capture_source=previous.capture_source,
        recorded_by=actor_id,
        captured_at=ts,
        revoked_at=ts,
        revoked_by=actor_id,
        is_current=True,
        created_at=ts,
    )
    db.add(row)
    db.flush()
    previous.superseded_by_id = row.id
    db.flush()
    return row


def list_current_consents(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
) -> list[CommunicationConsent]:
    patients_service.get_patient(db, tenant_id=tenant_id, patient_id=patient_id)
    return list(
        db.execute(
            select(CommunicationConsent)
            .where(
                CommunicationConsent.tenant_id == tenant_id,
                CommunicationConsent.patient_id == patient_id,
                CommunicationConsent.is_current.is_(True),
            )
            .order_by(CommunicationConsent.channel, CommunicationConsent.purpose)
        )
        .scalars()
        .all()
    )


# --- Communication log ---


def log_communication(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    patient_id: uuid.UUID,
    channel: str,
    purpose: str,
    outcome: str,
    location_id: uuid.UUID | None = None,
    follow_up_id: uuid.UUID | None = None,
    note: str | None = None,
    occurred_at: datetime | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> CommunicationLog:
    if channel not in M.COMM_CHANNELS:
        raise ValidationError("unknown channel")
    if purpose not in M.COMM_PURPOSES:
        raise ValidationError("unknown purpose")
    if outcome not in M.COMM_OUTCOMES:
        raise ValidationError("unknown outcome")
    cleaned_note = (note or "").strip() or None
    if cleaned_note and len(cleaned_note) > 280:
        raise ValidationError("note must be at most 280 characters")

    patients_service.get_patient(db, tenant_id=tenant_id, patient_id=patient_id)
    if location_id is not None:
        clinics_service.get_location(db, tenant_id=tenant_id, location_id=location_id)
        _check_location(location_ids, location_id)

    if follow_up_id is not None:
        fu = get_follow_up(
            db, tenant_id=tenant_id, follow_up_id=follow_up_id, location_ids=location_ids
        )
        if fu.patient_id != patient_id:
            raise ValidationError("follow-up belongs to a different patient")

    when = as_utc(occurred_at) if occurred_at is not None else now()
    row = CommunicationLog(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        patient_id=patient_id,
        location_id=location_id,
        follow_up_id=follow_up_id,
        channel=channel,
        purpose=purpose,
        outcome=outcome,
        staff_user_id=actor_id,
        occurred_at=when,
        note=cleaned_note,
        created_at=now(),
    )
    db.add(row)
    db.flush()
    return row


def list_communications(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID | None = None,
    follow_up_id: uuid.UUID | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
    limit: int = 50,
) -> list[CommunicationLog]:
    q = select(CommunicationLog).where(CommunicationLog.tenant_id == tenant_id)
    if patient_id is not None:
        q = q.where(CommunicationLog.patient_id == patient_id)
    if follow_up_id is not None:
        q = q.where(CommunicationLog.follow_up_id == follow_up_id)
    if location_ids:
        q = q.where(
            or_(
                CommunicationLog.location_id.is_(None),
                CommunicationLog.location_id.in_(list(location_ids)),
            )
        )
    capped = min(max(limit, 1), 200)
    return list(
        db.execute(q.order_by(CommunicationLog.occurred_at.desc()).limit(capped))
        .scalars()
        .all()
    )


def patient_followup_summary(
    db: DBSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID
) -> dict[str, int]:
    rows = list_follow_ups(
        db, tenant_id=tenant_id, patient_id=patient_id, limit=200
    )
    current = now()
    start_today = current.replace(hour=0, minute=0, second=0, microsecond=0)
    open_n = overdue_n = completed_n = 0
    for r in rows:
        if r.status == M.FU_COMPLETED:
            completed_n += 1
        elif r.status in (M.FU_OPEN, M.FU_IN_PROGRESS, M.FU_SNOOZED):
            open_n += 1
            if r.status != M.FU_SNOOZED and as_utc(r.due_at) < start_today:
                overdue_n += 1
    return {"open": open_n, "overdue": overdue_n, "completed": completed_n}
