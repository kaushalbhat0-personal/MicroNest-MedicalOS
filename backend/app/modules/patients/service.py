"""Patient identity service. Tenant-scoped reads/writes; cross-tenant probes
are indistinguishable from misses (NotFoundError, never a tenant oracle)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.modules.patients.models import Patient
from app.platform import ids
from app.platform.errors import NotFoundError, ValidationError
from app.platform.time import UTC


def _now() -> datetime:
    return datetime.now(UTC)


def register_patient(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    display_name: str,
    phone: str | None = None,
) -> Patient:
    name = (display_name or "").strip()
    if len(name) < 2 or len(name) > 200:
        raise ValidationError("display name must be 2-200 characters")
    digits = None
    if phone is not None:
        digits = phone.strip() or None
        if digits is not None and len(digits) > 32:
            raise ValidationError("phone must be at most 32 characters")
    now = _now()
    patient = Patient(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        display_name=name,
        phone=digits,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(patient)
    db.flush()
    return patient


def get_patient(db: DBSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID) -> Patient:
    patient = db.get(Patient, patient_id)
    if patient is None or patient.tenant_id != tenant_id:
        raise NotFoundError("patient not found")
    return patient


def list_patients(db: DBSession, *, tenant_id: uuid.UUID, limit: int = 50) -> list[Patient]:
    return list(
        db.execute(
            select(Patient)
            .where(Patient.tenant_id == tenant_id)
            .order_by(Patient.created_at.desc(), Patient.id.desc())
            .limit(min(max(limit, 1), 200))
        )
        .scalars()
        .all()
    )
