"""Patient identity service. Tenant-scoped reads/writes; cross-tenant probes
are indistinguishable from misses (NotFoundError, never a tenant oracle)."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session as DBSession

from app.modules.patients.models import Patient
from app.platform import ids
from app.platform.errors import NotFoundError, ValidationError
from app.platform.time import UTC

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,}$")


def _now() -> datetime:
    return datetime.now(UTC)


def _norm_phone(phone: str | None) -> str | None:
    if phone is None:
        return None
    digits = phone.strip() or None
    if digits is not None and len(digits) > 32:
        raise ValidationError("phone must be at most 32 characters")
    return digits


def _norm_email(email: str | None) -> str | None:
    if email is None:
        return None
    value = email.strip().lower() or None
    if value is None:
        return None
    if len(value) > 320 or not _EMAIL_RE.match(value):
        raise ValidationError("email is invalid")
    return value


def _norm_name(value: str | None, *, field: str, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise ValidationError(f"{field} is required")
        return None
    cleaned = value.strip()
    if not cleaned:
        if required:
            raise ValidationError(f"{field} is required")
        return None
    if len(cleaned) < 2 or len(cleaned) > 200:
        raise ValidationError(f"{field} must be 2-200 characters")
    return cleaned


def find_potential_duplicates(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    phone: str | None = None,
    email: str | None = None,
    exclude_id: uuid.UUID | None = None,
) -> list[Patient]:
    """Soft matches only — never a hard uniqueness constraint."""
    clauses = []
    if phone:
        clauses.append(Patient.phone == phone)
    if email:
        clauses.append(Patient.email == email)
    if not clauses:
        return []
    q = select(Patient).where(Patient.tenant_id == tenant_id, or_(*clauses))
    if exclude_id is not None:
        q = q.where(Patient.id != exclude_id)
    return list(db.execute(q.limit(10)).scalars().all())


def register_patient(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    display_name: str,
    phone: str | None = None,
    email: str | None = None,
    date_of_birth: date | None = None,
    emergency_contact_name: str | None = None,
    emergency_contact_phone: str | None = None,
) -> Patient:
    name = _norm_name(display_name, field="display name", required=True)
    assert name is not None
    digits = _norm_phone(phone)
    mail = _norm_email(email)
    emerg_name = _norm_name(emergency_contact_name, field="emergency contact name")
    emerg_phone = _norm_phone(emergency_contact_phone)
    if date_of_birth is not None and date_of_birth > _now().date():
        raise ValidationError("date of birth cannot be in the future")
    now = _now()
    patient = Patient(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        display_name=name,
        phone=digits,
        email=mail,
        date_of_birth=date_of_birth,
        emergency_contact_name=emerg_name,
        emergency_contact_phone=emerg_phone,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(patient)
    db.flush()
    return patient


def apply_patient_patch(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    fields: dict[str, object],
) -> Patient:
    """Patch only keys present in `fields` (explicit null clears)."""
    patient = get_patient(db, tenant_id=tenant_id, patient_id=patient_id)
    if "display_name" in fields:
        name = _norm_name(str(fields["display_name"]), field="display name", required=True)
        assert name is not None
        patient.display_name = name
    if "phone" in fields:
        raw = fields["phone"]
        patient.phone = _norm_phone(None if raw is None else str(raw))
    if "email" in fields:
        raw = fields["email"]
        patient.email = _norm_email(None if raw is None else str(raw))
    if "date_of_birth" in fields:
        dob = fields["date_of_birth"]
        if dob is not None and not isinstance(dob, date):
            raise ValidationError("date of birth is invalid")
        if isinstance(dob, date) and dob > _now().date():
            raise ValidationError("date of birth cannot be in the future")
        patient.date_of_birth = dob  # type: ignore[assignment]
    if "emergency_contact_name" in fields:
        raw = fields["emergency_contact_name"]
        patient.emergency_contact_name = _norm_name(
            None if raw is None else str(raw), field="emergency contact name"
        )
    if "emergency_contact_phone" in fields:
        raw = fields["emergency_contact_phone"]
        patient.emergency_contact_phone = _norm_phone(None if raw is None else str(raw))
    if "is_active" in fields:
        patient.is_active = bool(fields["is_active"])
    patient.updated_at = _now()
    db.flush()
    return patient


def get_patient(db: DBSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID) -> Patient:
    patient = db.get(Patient, patient_id)
    if patient is None or patient.tenant_id != tenant_id:
        raise NotFoundError("patient not found")
    return patient


def list_patients(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    limit: int = 50,
    q: str | None = None,
    active_only: bool = False,
) -> list[Patient]:
    query = select(Patient).where(Patient.tenant_id == tenant_id)
    if active_only:
        query = query.where(Patient.is_active.is_(True))
    term = (q or "").strip()
    if term:
        like = f"%{term}%"
        query = query.where(
            or_(
                Patient.display_name.ilike(like),
                Patient.phone.ilike(like),
                Patient.email.ilike(like),
            )
        )
    return list(
        db.execute(
            query.order_by(Patient.created_at.desc(), Patient.id.desc()).limit(
                min(max(limit, 1), 200)
            )
        )
        .scalars()
        .all()
    )


def import_patients(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    rows: list[dict[str, object]],
) -> tuple[int, int, int, list[dict[str, object]]]:
    """Import identity rows. Soft-skip exact phone/email duplicates in tenant."""
    created = skipped = errors = 0
    results: list[dict[str, object]] = []
    for idx, row in enumerate(rows, start=1):
        try:
            phone_raw = row.get("phone")
            email_raw = row.get("email")
            phone = _norm_phone(None if phone_raw is None else str(phone_raw))
            email = _norm_email(None if email_raw is None else str(email_raw))
            dups = find_potential_duplicates(db, tenant_id=tenant_id, phone=phone, email=email)
            if dups:
                skipped += 1
                results.append(
                    {
                        "row": idx,
                        "status": "skipped_duplicate",
                        "patient_id": dups[0].id,
                        "message": "matching phone or email already registered",
                    }
                )
                continue
            dob = row.get("date_of_birth")
            if dob is not None and not isinstance(dob, date):
                raise ValidationError("date of birth is invalid")
            emerg_name = row.get("emergency_contact_name")
            emerg_phone = row.get("emergency_contact_phone")
            patient = register_patient(
                db,
                tenant_id=tenant_id,
                display_name=str(row["display_name"]),
                phone=phone,
                email=email,
                date_of_birth=dob if isinstance(dob, date) else None,
                emergency_contact_name=None if emerg_name is None else str(emerg_name),
                emergency_contact_phone=None if emerg_phone is None else str(emerg_phone),
            )
            created += 1
            results.append(
                {"row": idx, "status": "created", "patient_id": patient.id, "message": None}
            )
        except (ValidationError, KeyError, TypeError, ValueError) as exc:
            errors += 1
            results.append(
                {
                    "row": idx,
                    "status": "error",
                    "patient_id": None,
                    "message": str(exc)[:200],
                }
            )
    return created, skipped, errors, results
