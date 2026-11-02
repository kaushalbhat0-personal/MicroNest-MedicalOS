"""Prescription service. Single authority for the draft → signed →
cancelled lifecycle and versioned corrections. Item content is immutable
once signed; a correction is a new draft version that must itself be
signed. Prescriber must be a verified practitioner."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.modules.clinical.service import get_encounter
from app.modules.identity.models import Practitioner
from app.modules.prescriptions import models as M
from app.modules.prescriptions.models import Medication, Prescription, PrescriptionItem
from app.modules.tenancy import service as tenancy_service
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
) -> object:
    enc = get_encounter(db, tenant_id=tenant_id, encounter_id=encounter_id)
    if location_ids and enc.location_id not in location_ids:
        raise ForbiddenError("location is outside your scope")
    return enc


def _verified_prescriber(
    db: DBSession, *, tenant_id: uuid.UUID, practitioner_id: uuid.UUID
) -> Practitioner:
    practitioner = db.get(Practitioner, practitioner_id)
    if practitioner is None or not practitioner.is_active:
        raise NotFoundError("practitioner not found")
    if not tenancy_service.is_practitioner_verified(
        db, tenant_id=tenant_id, practitioner_id=practitioner_id
    ):
        raise ForbiddenError("practitioner is not verified for this tenant")
    return practitioner


def get_medication(db: DBSession, *, code: str) -> Medication:
    med = db.execute(select(Medication).where(Medication.code == code)).scalar_one_or_none()
    if med is None or not med.is_active:
        raise ValidationError(f"unknown medication: {code}")
    return med


def list_medications(db: DBSession) -> list[Medication]:
    return list(
        db.execute(
            select(Medication).where(Medication.is_active.is_(True)).order_by(Medication.name)
        )
        .scalars()
        .all()
    )


def _add_items(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    prescription: Prescription,
    items: list[dict[str, object]],
    now: datetime,
) -> None:
    for line_no, raw in enumerate(items, start=1):
        med = get_medication(db, code=str(raw["medication_code"]))
        db.add(
            PrescriptionItem(
                id=ids.uuid7(),
                tenant_id=tenant_id,
                prescription_id=prescription.id,
                medication_id=med.id,
                line_no=line_no,
                dose=str(raw["dose"]),
                route=str(raw["route"]),
                frequency=str(raw["frequency"]),
                duration_days=raw.get("duration_days"),  # type: ignore[arg-type]
                quantity=raw.get("quantity"),  # type: ignore[arg-type]
                instructions=str(raw["instructions"]),
                created_at=now,
            )
        )


def create_prescription(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    encounter_id: uuid.UUID,
    prescribed_by: uuid.UUID,
    items: list[dict[str, object]],
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Prescription:
    _encounter_in_scope(
        db, tenant_id=tenant_id, encounter_id=encounter_id, location_ids=location_ids
    )
    _verified_prescriber(db, tenant_id=tenant_id, practitioner_id=prescribed_by)
    if not items:
        raise ValidationError("prescription requires at least one item")
    now = _now()
    rx = Prescription(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        encounter_id=encounter_id,
        prescribed_by=prescribed_by,
        status=M.RX_DRAFT,
        version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(rx)
    db.flush()
    _add_items(db, tenant_id=tenant_id, prescription=rx, items=items, now=now)
    db.flush()
    return rx


def get_prescription(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    prescription_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Prescription:
    rx = db.get(Prescription, prescription_id)
    if rx is None or rx.tenant_id != tenant_id:
        raise NotFoundError("prescription not found")
    if location_ids is not None:
        _encounter_in_scope(
            db,
            tenant_id=tenant_id,
            encounter_id=rx.encounter_id,
            location_ids=location_ids,
        )
    return rx


def list_prescriptions(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    encounter_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> list[Prescription]:
    _encounter_in_scope(
        db, tenant_id=tenant_id, encounter_id=encounter_id, location_ids=location_ids
    )
    return list(
        db.execute(
            select(Prescription)
            .where(Prescription.encounter_id == encounter_id)
            .order_by(Prescription.created_at, Prescription.id)
        )
        .scalars()
        .all()
    )


def sign_prescription(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    prescription_id: uuid.UUID,
    actor_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Prescription:
    rx = get_prescription(db, tenant_id=tenant_id, prescription_id=prescription_id)
    _encounter_in_scope(
        db, tenant_id=tenant_id, encounter_id=rx.encounter_id, location_ids=location_ids
    )
    if rx.status != M.RX_DRAFT:
        raise ConflictError("only draft prescriptions can be signed")
    if rx.prescribed_by != actor_id:
        raise ForbiddenError("only the prescriber can sign this prescription")
    rx.status = M.RX_SIGNED
    rx.signed_by = actor_id
    rx.signed_at = _now()
    rx.updated_at = rx.signed_at
    db.flush()
    return rx


def cancel_prescription(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    prescription_id: uuid.UUID,
    actor_id: uuid.UUID,
    reason: str | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Prescription:
    rx = get_prescription(db, tenant_id=tenant_id, prescription_id=prescription_id)
    _encounter_in_scope(
        db, tenant_id=tenant_id, encounter_id=rx.encounter_id, location_ids=location_ids
    )
    if rx.status == M.RX_CANCELLED:
        return rx
    if rx.status != M.RX_DRAFT and rx.status != M.RX_SIGNED:
        raise ConflictError("prescription cannot be cancelled")
    now = _now()
    rx.status = M.RX_CANCELLED
    rx.cancelled_by = actor_id
    rx.cancelled_at = now
    cleaned = (reason or "").strip() or None
    if cleaned is not None and len(cleaned) > 200:
        raise ValidationError("cancel reason must be at most 200 characters")
    rx.cancel_reason = cleaned
    rx.updated_at = now
    db.flush()
    return rx


def correct_prescription(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    prescription_id: uuid.UUID,
    prescribed_by: uuid.UUID,
    items: list[dict[str, object]],
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Prescription:
    """Correction = new draft version superseding the signed one. The signed
    row is never mutated except for the superseded_by link."""
    old = get_prescription(db, tenant_id=tenant_id, prescription_id=prescription_id)
    _encounter_in_scope(
        db, tenant_id=tenant_id, encounter_id=old.encounter_id, location_ids=location_ids
    )
    _verified_prescriber(db, tenant_id=tenant_id, practitioner_id=prescribed_by)
    if old.status != M.RX_SIGNED:
        raise ConflictError("only signed prescriptions can be corrected")
    if old.superseded_by_id is not None:
        raise ConflictError("prescription was already corrected")
    if not items:
        raise ValidationError("correction requires at least one item")
    now = _now()
    new = Prescription(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        encounter_id=old.encounter_id,
        prescribed_by=prescribed_by,
        status=M.RX_DRAFT,
        version=old.version + 1,
        supersedes_id=old.id,
        created_at=now,
        updated_at=now,
    )
    db.add(new)
    db.flush()
    _add_items(db, tenant_id=tenant_id, prescription=new, items=items, now=now)
    old.superseded_by_id = new.id
    old.updated_at = now
    db.flush()
    return new
