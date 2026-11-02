"""Clinical records service. Notes, observations, and diagnoses anchored to
encounters. Finalized content is immutable: corrections create superseding
rows and link the chain. No clinical text is ever logged or audited —
callers pass opaque IDs only."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.modules.clinical import models as M
from app.modules.clinical.models import (
    ClinicalNote,
    DiagnosisCode,
    Encounter,
    EncounterDiagnosis,
    Observation,
    ObservationType,
)
from app.modules.clinical.service import get_encounter
from app.modules.identity.models import Practitioner
from app.platform import ids
from app.platform.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.platform.time import UTC


def _now() -> datetime:
    return datetime.now(UTC)


def _encounter_in_scope(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    encounter_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None,
) -> Encounter:
    enc = get_encounter(db, tenant_id=tenant_id, encounter_id=encounter_id)
    if location_ids and enc.location_id not in location_ids:
        raise ForbiddenError("location is outside your scope")
    return enc


def _author_must_be_verified(
    db: DBSession, *, tenant_id: uuid.UUID, practitioner_id: uuid.UUID
) -> Practitioner:
    from app.modules.tenancy import service as tenancy_service

    practitioner = db.get(Practitioner, practitioner_id)
    if practitioner is None or not practitioner.is_active:
        raise NotFoundError("practitioner not found")
    if not tenancy_service.is_practitioner_verified(
        db, tenant_id=tenant_id, practitioner_id=practitioner_id
    ):
        raise ForbiddenError("practitioner is not verified for this tenant")
    return practitioner


# --- Notes ---


def _require_note_content(**fields: str | None) -> None:
    if not any((v or "").strip() for v in fields.values()):
        raise ValidationError("note requires at least one content field")


def create_note(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    encounter_id: uuid.UUID,
    author_id: uuid.UUID,
    note_type: str = "general",
    chief_complaint: str | None = None,
    subjective: str | None = None,
    objective: str | None = None,
    assessment: str | None = None,
    plan: str | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> ClinicalNote:
    enc = _encounter_in_scope(
        db, tenant_id=tenant_id, encounter_id=encounter_id, location_ids=location_ids
    )
    _author_must_be_verified(db, tenant_id=tenant_id, practitioner_id=author_id)
    _require_note_content(
        chief_complaint=chief_complaint,
        subjective=subjective,
        objective=objective,
        assessment=assessment,
        plan=plan,
    )
    now = _now()
    note = ClinicalNote(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        encounter_id=encounter_id,
        author_id=author_id,
        note_type=(note_type or "general").strip()[:40] or "general",
        chief_complaint=(chief_complaint or "").strip() or None,
        subjective=(subjective or "").strip() or None,
        objective=(objective or "").strip() or None,
        assessment=(assessment or "").strip() or None,
        plan=(plan or "").strip() or None,
        status=M.NOTE_DRAFT,
        version=1,
        is_addendum=bool(enc.status == M.ENCOUNTER_CLOSED),
        created_at=now,
        updated_at=now,
    )
    db.add(note)
    db.flush()
    return note


def get_note(db: DBSession, *, tenant_id: uuid.UUID, note_id: uuid.UUID) -> ClinicalNote:
    note = db.get(ClinicalNote, note_id)
    if note is None or note.tenant_id != tenant_id:
        raise NotFoundError("note not found")
    return note


def list_notes(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    encounter_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> list[ClinicalNote]:
    _encounter_in_scope(
        db, tenant_id=tenant_id, encounter_id=encounter_id, location_ids=location_ids
    )
    return list(
        db.execute(
            select(ClinicalNote)
            .where(ClinicalNote.encounter_id == encounter_id)
            .order_by(ClinicalNote.created_at, ClinicalNote.id)
        )
        .scalars()
        .all()
    )


def finalize_note(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    note_id: uuid.UUID,
    actor_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> ClinicalNote:
    note = get_note(db, tenant_id=tenant_id, note_id=note_id)
    _encounter_in_scope(
        db, tenant_id=tenant_id, encounter_id=note.encounter_id, location_ids=location_ids
    )
    if note.status != M.NOTE_DRAFT:
        raise ConflictError("only draft notes can be finalized")
    if note.author_id != actor_id:
        raise ForbiddenError("only the author can finalize this note")
    note.status = M.NOTE_FINALIZED
    note.version += 1
    note.updated_at = _now()
    db.flush()
    return note


def amend_note(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    note_id: uuid.UUID,
    actor_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
    **fields: str | None,
) -> ClinicalNote:
    """Correction = new finalized note superseding the old one. The old row
    is never mutated except for the superseded_by link."""
    old = get_note(db, tenant_id=tenant_id, note_id=note_id)
    _encounter_in_scope(
        db, tenant_id=tenant_id, encounter_id=old.encounter_id, location_ids=location_ids
    )
    _author_must_be_verified(db, tenant_id=tenant_id, practitioner_id=actor_id)
    if old.status != M.NOTE_FINALIZED:
        raise ConflictError("only finalized notes can be amended")
    if old.superseded_by_id is not None:
        raise ConflictError("note was already amended")
    _require_note_content(**fields)
    now = _now()
    new = ClinicalNote(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        encounter_id=old.encounter_id,
        author_id=actor_id,
        note_type=old.note_type,
        chief_complaint=(fields.get("chief_complaint") or "").strip() or None,
        subjective=(fields.get("subjective") or "").strip() or None,
        objective=(fields.get("objective") or "").strip() or None,
        assessment=(fields.get("assessment") or "").strip() or None,
        plan=(fields.get("plan") or "").strip() or None,
        status=M.NOTE_FINALIZED,
        version=old.version + 1,
        is_addendum=old.is_addendum,
        supersedes_id=old.id,
        created_at=now,
        updated_at=now,
    )
    db.add(new)
    db.flush()
    old.status = M.NOTE_AMENDED
    old.superseded_by_id = new.id
    old.updated_at = now
    db.flush()
    return new


# --- Observations ---


def get_observation_type(db: DBSession, *, code: str) -> ObservationType:
    otype = db.execute(
        select(ObservationType).where(ObservationType.code == code)
    ).scalar_one_or_none()
    if otype is None or not otype.is_active:
        raise ValidationError(f"unknown observation type: {code}")
    return otype


def list_observation_types(db: DBSession) -> list[ObservationType]:
    return list(
        db.execute(
            select(ObservationType)
            .where(ObservationType.is_active.is_(True))
            .order_by(ObservationType.display)
        )
        .scalars()
        .all()
    )


def record_observation(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    encounter_id: uuid.UUID,
    type_code: str,
    value_numeric: float,
    value_text: str | None = None,
    taken_at: datetime | None = None,
    recorded_by: uuid.UUID | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Observation:
    _encounter_in_scope(
        db, tenant_id=tenant_id, encounter_id=encounter_id, location_ids=location_ids
    )
    otype = get_observation_type(db, code=type_code)
    low = float(otype.min_value) if otype.min_value is not None else None
    high = float(otype.max_value) if otype.max_value is not None else None
    if (low is not None and value_numeric < low) or (high is not None and value_numeric > high):
        raise ValidationError(f"{otype.code} out of range ({low}–{high} {otype.unit})")
    now = _now()
    obs = Observation(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        encounter_id=encounter_id,
        type_id=otype.id,
        value_numeric=value_numeric,
        value_text=(value_text or "").strip() or None,
        unit=otype.unit,
        taken_at=taken_at or now,
        recorded_by=recorded_by,
        created_at=now,
    )
    db.add(obs)
    db.flush()
    return obs


def get_observation(
    db: DBSession, *, tenant_id: uuid.UUID, observation_id: uuid.UUID
) -> Observation:
    obs = db.get(Observation, observation_id)
    if obs is None or obs.tenant_id != tenant_id:
        raise NotFoundError("observation not found")
    return obs


def list_observations(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    encounter_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> list[Observation]:
    _encounter_in_scope(
        db, tenant_id=tenant_id, encounter_id=encounter_id, location_ids=location_ids
    )
    return list(
        db.execute(
            select(Observation)
            .where(Observation.encounter_id == encounter_id)
            .order_by(Observation.taken_at, Observation.id)
        )
        .scalars()
        .all()
    )


def amend_observation(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    observation_id: uuid.UUID,
    value_numeric: float,
    value_text: str | None = None,
    recorded_by: uuid.UUID | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Observation:
    old = get_observation(db, tenant_id=tenant_id, observation_id=observation_id)
    _encounter_in_scope(
        db, tenant_id=tenant_id, encounter_id=old.encounter_id, location_ids=location_ids
    )
    if old.corrected_by_id is not None:
        raise ConflictError("observation was already corrected")
    otype = db.get(ObservationType, old.type_id)
    assert otype is not None
    low = float(otype.min_value) if otype.min_value is not None else None
    high = float(otype.max_value) if otype.max_value is not None else None
    if (low is not None and value_numeric < low) or (high is not None and value_numeric > high):
        raise ValidationError(f"{otype.code} out of range ({low}–{high} {otype.unit})")
    now = _now()
    new = Observation(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        encounter_id=old.encounter_id,
        type_id=old.type_id,
        value_numeric=value_numeric,
        value_text=(value_text or "").strip() or None,
        unit=otype.unit,
        taken_at=old.taken_at,
        recorded_by=recorded_by,
        corrects_id=old.id,
        created_at=now,
    )
    db.add(new)
    db.flush()
    old.corrected_by_id = new.id
    db.flush()
    return new


# --- Diagnoses ---


def get_diagnosis_code(db: DBSession, *, code: str) -> DiagnosisCode:
    row = db.execute(select(DiagnosisCode).where(DiagnosisCode.code == code)).scalar_one_or_none()
    if row is None or not row.is_active:
        raise ValidationError(f"unknown diagnosis code: {code}")
    return row


def list_diagnosis_codes(db: DBSession) -> list[DiagnosisCode]:
    return list(
        db.execute(
            select(DiagnosisCode)
            .where(DiagnosisCode.is_active.is_(True))
            .order_by(DiagnosisCode.display)
        )
        .scalars()
        .all()
    )


def add_diagnosis(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    encounter_id: uuid.UUID,
    diagnosis_code: str | None = None,
    free_text: str | None = None,
    is_primary: bool = False,
    onset_date: object = None,
    recorded_by: uuid.UUID | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> EncounterDiagnosis:
    _encounter_in_scope(
        db, tenant_id=tenant_id, encounter_id=encounter_id, location_ids=location_ids
    )
    code_row = None
    cleaned_free = (free_text or "").strip() or None
    if (diagnosis_code is None) == (cleaned_free is None):
        raise ValidationError("provide exactly one of diagnosis_code or free_text")
    if diagnosis_code is not None:
        code_row = get_diagnosis_code(db, code=diagnosis_code)
    now = _now()
    dx = EncounterDiagnosis(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        encounter_id=encounter_id,
        diagnosis_id=code_row.id if code_row else None,
        free_text=cleaned_free,
        is_primary=is_primary,
        status=M.DX_ACTIVE,
        review_needed=bool(code_row.needs_review) if code_row else True,
        onset_date=onset_date,  # type: ignore[arg-type]
        recorded_by=recorded_by,
        created_at=now,
        updated_at=now,
    )
    db.add(dx)
    db.flush()
    return dx


def get_diagnosis(
    db: DBSession, *, tenant_id: uuid.UUID, diagnosis_id: uuid.UUID
) -> EncounterDiagnosis:
    dx = db.get(EncounterDiagnosis, diagnosis_id)
    if dx is None or dx.tenant_id != tenant_id:
        raise NotFoundError("diagnosis not found")
    return dx


def list_diagnoses(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    encounter_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> list[EncounterDiagnosis]:
    _encounter_in_scope(
        db, tenant_id=tenant_id, encounter_id=encounter_id, location_ids=location_ids
    )
    return list(
        db.execute(
            select(EncounterDiagnosis)
            .where(EncounterDiagnosis.encounter_id == encounter_id)
            .order_by(EncounterDiagnosis.created_at, EncounterDiagnosis.id)
        )
        .scalars()
        .all()
    )


def resolve_diagnosis(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    diagnosis_id: uuid.UUID,
    outcome: str,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> EncounterDiagnosis:
    if outcome not in (M.DX_RESOLVED, M.DX_RULED_OUT):
        raise ValidationError("unknown outcome")
    dx = get_diagnosis(db, tenant_id=tenant_id, diagnosis_id=diagnosis_id)
    _encounter_in_scope(
        db, tenant_id=tenant_id, encounter_id=dx.encounter_id, location_ids=location_ids
    )
    if dx.status != M.DX_ACTIVE:
        raise ConflictError("only active diagnoses can be resolved")
    dx.status = outcome
    dx.updated_at = _now()
    db.flush()
    return dx


def supersede_diagnosis(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    diagnosis_id: uuid.UUID,
    recorded_by: uuid.UUID | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
    diagnosis_code: str | None = None,
    free_text: str | None = None,
    is_primary: bool = False,
) -> EncounterDiagnosis:
    """Correction = new active row superseding the old one."""
    old = get_diagnosis(db, tenant_id=tenant_id, diagnosis_id=diagnosis_id)
    _encounter_in_scope(
        db, tenant_id=tenant_id, encounter_id=old.encounter_id, location_ids=location_ids
    )
    if old.status != M.DX_ACTIVE:
        raise ConflictError("only active diagnoses can be superseded")
    if old.superseded_by_id is not None:
        raise ConflictError("diagnosis was already superseded")
    new = add_diagnosis(
        db,
        tenant_id=tenant_id,
        encounter_id=old.encounter_id,
        diagnosis_code=diagnosis_code,
        free_text=free_text,
        is_primary=is_primary,
        recorded_by=recorded_by,
        location_ids=location_ids,
    )
    new.supersedes_id = old.id
    old.status = M.DX_SUPERSEDED
    old.superseded_by_id = new.id
    old.updated_at = _now()
    db.flush()
    return new
