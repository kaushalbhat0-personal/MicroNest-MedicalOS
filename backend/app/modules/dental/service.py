"""Dental findings + catalogs service. Single authority for FDI tooth
identity, tooth-surface validation, and finding lifecycle.

P3 covers permanent dentition (FDI 11–18, 21–28, 31–38, 41–48).
Primary dentition (51–85) is explicitly deferred — the validator is the one
place that rule lives, so extending it later is a single change.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.modules.clinical.service import get_encounter
from app.modules.dental import models as M
from app.modules.dental.models import DentalCondition, DentalProcedure, ToothFinding
from app.modules.identity.models import Practitioner
from app.modules.tenancy import service as tenancy_service
from app.platform import ids
from app.platform.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.platform.time import UTC

# Permanent dentition, FDI two-digit notation.
PERMANENT_TEETH = frozenset(
    list(range(11, 19)) + list(range(21, 29)) + list(range(31, 39)) + list(range(41, 49))
)

# Domain-controlled surface set. Anterior/posterior appropriateness is not
# enforced in P3 (documented); free-form strings are rejected.
SURFACES = frozenset(
    {"mesial", "distal", "occlusal", "incisal", "buccal", "labial", "lingual", "palatal"}
)


def validate_tooth(tooth: int | None) -> None:
    if tooth is None:
        return
    if tooth not in PERMANENT_TEETH:
        raise ValidationError(f"unsupported tooth number: {tooth} (P3: permanent dentition only)")


def validate_surfaces(surfaces: list[str]) -> list[str]:
    cleaned = [(s or "").strip().lower() for s in surfaces]
    if len(set(cleaned)) != len(cleaned):
        raise ValidationError("duplicate surfaces")
    for s in cleaned:
        if s not in SURFACES:
            raise ValidationError(f"unsupported tooth surface: {s}")
    return cleaned


def validate_surface(surface: str | None) -> str | None:
    if surface is None:
        return None
    s = surface.strip().lower()
    if s not in SURFACES:
        raise ValidationError(f"unsupported tooth surface: {surface}")
    return s


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


def _verified_practitioner(
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


def get_condition(db: DBSession, *, code: str) -> DentalCondition:
    cond = db.execute(
        select(DentalCondition).where(DentalCondition.code == code)
    ).scalar_one_or_none()
    if cond is None or not cond.is_active:
        raise ValidationError(f"unknown dental condition: {code}")
    return cond


def list_conditions(db: DBSession) -> list[DentalCondition]:
    return list(
        db.execute(
            select(DentalCondition)
            .where(DentalCondition.is_active.is_(True))
            .order_by(DentalCondition.display)
        )
        .scalars()
        .all()
    )


def get_procedure(db: DBSession, *, code: str) -> DentalProcedure:
    proc = db.execute(
        select(DentalProcedure).where(DentalProcedure.code == code)
    ).scalar_one_or_none()
    if proc is None or not proc.is_active:
        raise ValidationError(f"unknown dental procedure: {code}")
    return proc


def list_procedures(db: DBSession) -> list[DentalProcedure]:
    return list(
        db.execute(
            select(DentalProcedure)
            .where(DentalProcedure.is_active.is_(True))
            .order_by(DentalProcedure.display)
        )
        .scalars()
        .all()
    )


def record_finding(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    encounter_id: uuid.UUID,
    practitioner_id: uuid.UUID,
    tooth: int,
    condition_code: str,
    surfaces: list[str] | None = None,
    details: str | None = None,
    recorded_by: uuid.UUID | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> ToothFinding:
    _encounter_in_scope(
        db, tenant_id=tenant_id, encounter_id=encounter_id, location_ids=location_ids
    )
    _verified_practitioner(db, tenant_id=tenant_id, practitioner_id=practitioner_id)
    validate_tooth(tooth)
    clean_surfaces = validate_surfaces(surfaces or [])
    cond = get_condition(db, code=condition_code)
    now = _now()
    finding = ToothFinding(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        encounter_id=encounter_id,
        practitioner_id=practitioner_id,
        tooth=tooth,
        condition_id=cond.id,
        status=M.FINDING_ACTIVE,
        details=(details or "").strip() or None,
        recorded_by=recorded_by,
        created_at=now,
        updated_at=now,
    )
    db.add(finding)
    db.flush()
    for s in clean_surfaces:
        db.add(
            M.ToothFindingSurface(
                id=ids.uuid7(),
                tenant_id=tenant_id,
                finding_id=finding.id,
                surface=s,
            )
        )
    db.flush()
    return finding


def get_finding(db: DBSession, *, tenant_id: uuid.UUID, finding_id: uuid.UUID) -> ToothFinding:
    finding = db.get(ToothFinding, finding_id)
    if finding is None or finding.tenant_id != tenant_id:
        raise NotFoundError("finding not found")
    return finding


def finding_surfaces(db: DBSession, *, finding_id: uuid.UUID) -> list[str]:
    return list(
        db.execute(
            select(M.ToothFindingSurface.surface)
            .where(M.ToothFindingSurface.finding_id == finding_id)
            .order_by(M.ToothFindingSurface.surface)
        )
        .scalars()
        .all()
    )


def list_findings(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    encounter_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> list[ToothFinding]:
    _encounter_in_scope(
        db, tenant_id=tenant_id, encounter_id=encounter_id, location_ids=location_ids
    )
    return list(
        db.execute(
            select(ToothFinding)
            .where(ToothFinding.encounter_id == encounter_id)
            .order_by(ToothFinding.tooth, ToothFinding.created_at)
        )
        .scalars()
        .all()
    )


def resolve_finding(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    finding_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> ToothFinding:
    finding = get_finding(db, tenant_id=tenant_id, finding_id=finding_id)
    _encounter_in_scope(
        db, tenant_id=tenant_id, encounter_id=finding.encounter_id, location_ids=location_ids
    )
    if finding.status != M.FINDING_ACTIVE:
        raise ConflictError("only active findings can be resolved")
    finding.status = M.FINDING_RESOLVED
    finding.updated_at = _now()
    db.flush()
    return finding
