"""Encounter service. Single source of truth for the encounter lifecycle.

Open encounters accept care; closed encounters are terminal — clinical facts
are then immutable and corrections flow through supersede chains owned by
the records module. The closure ceremony enforces: provider attribution,
note-or-waiver, vitals-or-waiver, and an open-items check (draft
prescriptions and draft treatment plans linked to the encounter).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.modules.clinical import models as M
from app.modules.clinical.models import Encounter
from app.modules.clinics import service as clinics_service
from app.modules.identity.models import Practitioner
from app.modules.patients import service as patients_service
from app.modules.scheduling.models import Appointment
from app.modules.tenancy import service as tenancy_service
from app.platform import ids
from app.platform.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.platform.time import UTC


def _now() -> datetime:
    return datetime.now(UTC)


def _encounter_scope(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    practitioner_id: uuid.UUID,
    location_id: uuid.UUID,
    appointment_id: uuid.UUID | None,
    location_ids: frozenset[uuid.UUID] | None,
) -> tuple[object, Practitioner, object, Appointment | None]:
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
    if location_ids and location_id not in location_ids:
        raise ForbiddenError("location is outside your scope")
    appointment = None
    if appointment_id is not None:
        appointment = db.get(Appointment, appointment_id)
        if appointment is None or appointment.tenant_id != tenant_id:
            raise NotFoundError("appointment not found")
        if appointment.patient_id != patient_id:
            raise ValidationError("appointment does not belong to this patient")
    return patient, practitioner, location, appointment


def open_encounter(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    patient_id: uuid.UUID,
    practitioner_id: uuid.UUID,
    location_id: uuid.UUID,
    appointment_id: uuid.UUID | None = None,
    chief_complaint: str | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Encounter:
    _encounter_scope(
        db,
        tenant_id=tenant_id,
        patient_id=patient_id,
        practitioner_id=practitioner_id,
        location_id=location_id,
        appointment_id=appointment_id,
        location_ids=location_ids,
    )
    now = _now()
    enc = Encounter(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        patient_id=patient_id,
        practitioner_id=practitioner_id,
        location_id=location_id,
        appointment_id=appointment_id,
        chief_complaint=(chief_complaint or "").strip() or None,
        status=M.ENCOUNTER_OPEN,
        version=1,
        opened_by=actor_id,
        opened_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(enc)
    db.flush()
    return enc


def get_encounter(db: DBSession, *, tenant_id: uuid.UUID, encounter_id: uuid.UUID) -> Encounter:
    enc = db.get(Encounter, encounter_id)
    if enc is None or enc.tenant_id != tenant_id:
        raise NotFoundError("encounter not found")
    return enc


def list_encounters(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
    patient_id: uuid.UUID | None = None,
    practitioner_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    status: str | None = None,
    limit: int = 50,
    cursor: uuid.UUID | None = None,
) -> tuple[list[Encounter], uuid.UUID | None]:
    """Keyset page over (opened_at, id)."""
    if location_id is not None and location_ids and location_id not in location_ids:
        raise ForbiddenError("location is outside your scope")
    q = select(Encounter).where(Encounter.tenant_id == tenant_id)
    if location_ids:
        q = q.where(Encounter.location_id.in_(list(location_ids)))
    if patient_id is not None:
        q = q.where(Encounter.patient_id == patient_id)
    if practitioner_id is not None:
        q = q.where(Encounter.practitioner_id == practitioner_id)
    if location_id is not None:
        q = q.where(Encounter.location_id == location_id)
    if status is not None:
        if status not in M.ENCOUNTER_STATUSES:
            raise ValidationError("unknown status")
        q = q.where(Encounter.status == status)
    if cursor is not None:
        anchor = get_encounter(db, tenant_id=tenant_id, encounter_id=cursor)
        q = q.where(
            (Encounter.opened_at > anchor.opened_at)
            | ((Encounter.opened_at == anchor.opened_at) & (Encounter.id > anchor.id))
        )
    capped = min(max(limit, 1), 200)
    rows = list(
        db.execute(q.order_by(Encounter.opened_at, Encounter.id).limit(capped + 1)).scalars().all()
    )
    if len(rows) > capped:
        return rows[:-1], rows[-2].id
    return rows, None


def _open_items_block(db: DBSession, *, encounter_id: uuid.UUID) -> list[str]:
    """Draft prescriptions and draft treatment plans linked to the encounter
    block closure until they are signed/activated or cancelled."""
    from app.modules.dental.models import TreatmentPlan
    from app.modules.prescriptions.models import Prescription

    blockers: list[str] = []
    drafts_rx = (
        db.execute(
            select(Prescription.id).where(
                Prescription.encounter_id == encounter_id,
                Prescription.status == "draft",
            )
        )
        .scalars()
        .all()
    )
    if drafts_rx:
        blockers.append(f"{len(drafts_rx)} unsigned prescription(s)")
    drafts_plan = (
        db.execute(
            select(TreatmentPlan.id).where(
                TreatmentPlan.encounter_id == encounter_id,
                TreatmentPlan.status == "draft",
            )
        )
        .scalars()
        .all()
    )
    if drafts_plan:
        blockers.append(f"{len(drafts_plan)} draft treatment plan(s)")
    return blockers


def close_encounter(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    encounter_id: uuid.UUID,
    actor_id: uuid.UUID,
    note_waiver: bool = False,
    vitals_waiver: bool = False,
    reason: str | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Encounter:
    enc = get_encounter(db, tenant_id=tenant_id, encounter_id=encounter_id)
    if enc.status != M.ENCOUNTER_OPEN:
        raise ConflictError("encounter is already closed")
    if location_ids and enc.location_id not in location_ids:
        raise ForbiddenError("location is outside your scope")
    if not note_waiver:
        finalized = db.execute(
            select(M.ClinicalNote.id).where(
                M.ClinicalNote.encounter_id == enc.id,
                M.ClinicalNote.status == M.NOTE_FINALIZED,
            )
        ).first()
        if finalized is None:
            raise ValidationError("closure requires a finalized note or an explicit waiver")
    if not vitals_waiver:
        vitals = db.execute(
            select(M.Observation.id).where(M.Observation.encounter_id == enc.id)
        ).first()
        if vitals is None:
            raise ValidationError("closure requires vitals or an explicit waiver")
    blockers = _open_items_block(db, encounter_id=enc.id)
    if blockers:
        raise ConflictError("open items block closure: " + "; ".join(blockers))
    now = _now()
    enc.status = M.ENCOUNTER_CLOSED
    enc.version += 1
    enc.closed_by = actor_id
    enc.closed_at = now
    cleaned = (reason or "").strip() or None
    if cleaned is not None and len(cleaned) > 200:
        raise ValidationError("close reason must be at most 200 characters")
    enc.close_reason = cleaned
    enc.updated_at = now
    db.flush()
    return enc
