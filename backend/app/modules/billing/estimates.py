"""Estimate service. Single authority for the estimate lifecycle.

Draft estimates are editable (lines may change); issued estimates are frozen
snapshots. Conversion to invoices snapshots selected lines (P4.4 owns the
converter; this module owns the transition map it will use). Corrections to
issued estimates create a new estimate version superseding the old one.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.modules.billing import models as M
from app.modules.billing import money as moneylib
from app.modules.billing import service_catalog as catalog_svc
from app.modules.billing.models import Estimate, EstimateLine
from app.modules.clinical.service import get_encounter
from app.modules.clinics import service as clinics_service
from app.modules.identity.models import Practitioner
from app.modules.patients import service as patients_service
from app.modules.tenancy import service as tenancy_service
from app.platform import ids
from app.platform.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.platform.time import UTC


def _now() -> datetime:
    return datetime.now(UTC)


ESTIMATE_TRANSITIONS: dict[str, frozenset[str]] = {
    M.ESTIMATE_DRAFT: frozenset({M.ESTIMATE_ISSUED, M.ESTIMATE_CANCELLED}),
    M.ESTIMATE_ISSUED: frozenset({M.ESTIMATE_CONVERTED, M.ESTIMATE_EXPIRED, M.ESTIMATE_CANCELLED}),
    M.ESTIMATE_CONVERTED: frozenset(),
    M.ESTIMATE_EXPIRED: frozenset(),
    M.ESTIMATE_CANCELLED: frozenset(),
}


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


def _estimate_in_scope(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    estimate: Estimate,
    location_ids: frozenset[uuid.UUID] | None,
) -> None:
    """Fail-closed location scope. Encounter-linked rows resolve through the
    encounter; encounter-less rows pin their own location (dental plan
    fail-closed pattern)."""
    if not location_ids:
        return
    if estimate.encounter_id is not None:
        enc = get_encounter(db, tenant_id=tenant_id, encounter_id=estimate.encounter_id)
        if enc.location_id not in location_ids:
            raise ForbiddenError("location is outside your scope")
    elif estimate.location_id not in location_ids:
        raise ForbiddenError("location is outside your scope")


def _validate_refs(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    location_id: uuid.UUID,
    practitioner_id: uuid.UUID | None,
    encounter_id: uuid.UUID | None,
    location_ids: frozenset[uuid.UUID] | None,
) -> None:
    patient = patients_service.get_patient(db, tenant_id=tenant_id, patient_id=patient_id)
    if not patient.is_active:
        raise ValidationError("patient is not active")
    location = clinics_service.get_location(db, tenant_id=tenant_id, location_id=location_id)
    if not location.is_active:
        raise ValidationError("location is not active")
    if practitioner_id is not None:
        _verified_practitioner(db, tenant_id=tenant_id, practitioner_id=practitioner_id)
    if encounter_id is not None:
        enc = get_encounter(db, tenant_id=tenant_id, encounter_id=encounter_id)
        if enc.patient_id != patient_id:
            raise ValidationError("encounter does not belong to this patient")
        if enc.location_id != location_id:
            raise ValidationError("estimate location must match the encounter location")
        if location_ids and enc.location_id not in location_ids:
            raise ForbiddenError("location is outside your scope")
    elif location_ids and location_id not in location_ids:
        raise ForbiddenError("location is outside your scope")


def get_estimate(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    estimate_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Estimate:
    est = db.get(Estimate, estimate_id)
    if est is None or est.tenant_id != tenant_id:
        raise NotFoundError("estimate not found")
    _estimate_in_scope(db, tenant_id=tenant_id, estimate=est, location_ids=location_ids)
    return est


def estimate_lines(db: DBSession, *, estimate_id: uuid.UUID) -> list[EstimateLine]:
    return list(
        db.execute(
            select(EstimateLine)
            .where(EstimateLine.estimate_id == estimate_id)
            .order_by(EstimateLine.sequence, EstimateLine.id)
        )
        .scalars()
        .all()
    )


def list_estimates(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID | None = None,
    status: str | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
    limit: int = 50,
    cursor: uuid.UUID | None = None,
) -> tuple[list[Estimate], uuid.UUID | None]:
    """Keyset page over (created_at, id). Location filter pins the estimate's
    own location (creation forces equality with any linked encounter)."""
    if status is not None and status not in M.ESTIMATE_STATUSES:
        raise ValidationError("unknown status")
    q = select(Estimate).where(Estimate.tenant_id == tenant_id)
    if location_ids:
        q = q.where(Estimate.location_id.in_(list(location_ids)))
    if patient_id is not None:
        q = q.where(Estimate.patient_id == patient_id)
    if status is not None:
        q = q.where(Estimate.status == status)
    if cursor is not None:
        anchor = get_estimate(db, tenant_id=tenant_id, estimate_id=cursor)
        q = q.where(
            (Estimate.created_at > anchor.created_at)
            | ((Estimate.created_at == anchor.created_at) & (Estimate.id > anchor.id))
        )
    capped = min(max(limit, 1), 200)
    rows = list(
        db.execute(q.order_by(Estimate.created_at, Estimate.id).limit(capped + 1)).scalars().all()
    )
    if len(rows) > capped:
        return rows[:-1], rows[-2].id
    return rows, None


def _snapshot_line(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    estimate_id: uuid.UUID,
    service_catalog_id: uuid.UUID | None,
    description: str | None,
    quantity: object,
    unit_rate: object | None,
    discount_amount: object,
    tax_rate: object | None,
    hsn_sac: str | None,
    tax_treatment: str | None,
    sequence: int,
) -> EstimateLine:
    """Resolve catalog defaults, then snapshot everything into the row.
    Post-creation catalog edits never touch this row."""
    catalog_item = None
    if service_catalog_id is not None:
        catalog_item = catalog_svc.get_service(db, item_id=service_catalog_id)
        if not catalog_item.is_active:
            raise ValidationError("catalog service is not active")
    desc = (description or "").strip() or (catalog_item.display if catalog_item else "").strip()
    if not desc or len(desc) > 300:
        raise ValidationError("line description must be 1-300 characters")
    rate = (
        moneylib.ensure_decimal(unit_rate, field="unit_rate")
        if unit_rate is not None
        else (catalog_item.default_rate if catalog_item else 0)
    )
    rate = moneylib.ensure_decimal(rate, field="unit_rate")
    tax = (
        moneylib.ensure_decimal(tax_rate, field="tax_rate")
        if tax_rate is not None
        else (catalog_item.tax_rate if catalog_item else 0)
    )
    tax = moneylib.ensure_decimal(tax, field="tax_rate")
    if tax < 0 or tax > 100:
        raise ValidationError("tax rate must be between 0 and 100")
    hsn = (hsn_sac or "").strip() or (catalog_item.hsn_sac if catalog_item else None)
    if hsn is not None and len(hsn) > 16:
        raise ValidationError("hsn/sac must be at most 16 characters")
    treatment = (tax_treatment or "").strip().lower() or M.TAX_TAXABLE
    if treatment not in M.TAX_TREATMENTS:
        raise ValidationError("unknown tax treatment")
    computed = moneylib.compute_line_total(
        quantity=quantity,
        unit_rate=rate,
        discount_amount=discount_amount,
        tax_rate_percent=tax,
    )
    now = _now()
    return EstimateLine(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        estimate_id=estimate_id,
        service_catalog_id=service_catalog_id,
        description=desc,
        quantity=moneylib.ensure_decimal(quantity, field="quantity"),
        unit_rate=rate,
        discount_amount=moneylib.ensure_decimal(discount_amount, field="discount_amount"),
        taxable_amount=computed["taxable_amount"],
        tax_rate=tax,
        tax_amount=computed["tax_amount"],
        hsn_sac=hsn,
        tax_treatment=treatment,
        line_total=computed["line_total"],
        sequence=sequence,
        created_at=now,
    )


def _recalc_totals(db: DBSession, *, estimate: Estimate) -> None:
    lines = estimate_lines(db, estimate_id=estimate.id)
    subtotal = sum((moneylib.ensure_decimal(line.taxable_amount) for line in lines), Decimal(0))
    tax_total = sum((moneylib.ensure_decimal(line.tax_amount) for line in lines), Decimal(0))
    estimate.subtotal = moneylib.quantize_half_up(subtotal)
    estimate.tax_total = moneylib.quantize_half_up(tax_total)
    estimate.grand_total = moneylib.compute_invoice_total([line.line_total for line in lines])
    estimate.updated_at = _now()


def create_estimate(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    patient_id: uuid.UUID,
    location_id: uuid.UUID,
    practitioner_id: uuid.UUID | None = None,
    encounter_id: uuid.UUID | None = None,
    treatment_plan_id: uuid.UUID | None = None,
    valid_until: date | None = None,
    notes: str | None = None,
    items: list[dict[str, object]] | None = None,
    idempotency_key: str | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Estimate:
    _validate_refs(
        db,
        tenant_id=tenant_id,
        patient_id=patient_id,
        location_id=location_id,
        practitioner_id=practitioner_id,
        encounter_id=encounter_id,
        location_ids=location_ids,
    )
    if idempotency_key:
        existing = db.execute(
            select(Estimate).where(
                Estimate.tenant_id == tenant_id,
                Estimate.idempotency_key == idempotency_key,
            )
        ).scalar_one_or_none()
        if existing is not None:
            if existing.patient_id != patient_id or existing.location_id != location_id:
                raise ConflictError("idempotency key was used for a different estimate")
            return existing
    now = _now()
    est = Estimate(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        location_id=location_id,
        patient_id=patient_id,
        encounter_id=encounter_id,
        treatment_plan_id=treatment_plan_id,
        practitioner_id=practitioner_id,
        status=M.ESTIMATE_DRAFT,
        version=1,
        valid_until=valid_until,
        notes=(notes or "").strip() or None,
        idempotency_key=(idempotency_key or "").strip() or None,
        created_by=actor_id,
        created_at=now,
        updated_at=now,
    )
    if est.notes is not None and len(est.notes) > 500:
        raise ValidationError("notes must be at most 500 characters")
    db.add(est)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ConflictError("idempotency key was used for a different estimate") from None
    for position, raw in enumerate(items or [], start=1):
        db.add(
            _snapshot_line(
                db,
                tenant_id=tenant_id,
                estimate_id=est.id,
                service_catalog_id=raw.get("service_catalog_id"),  # type: ignore[arg-type]
                description=raw.get("description"),  # type: ignore[arg-type]
                quantity=raw.get("quantity", 1),
                unit_rate=raw.get("unit_rate"),
                discount_amount=raw.get("discount_amount", 0),
                tax_rate=raw.get("tax_rate"),
                hsn_sac=raw.get("hsn_sac"),  # type: ignore[arg-type]
                tax_treatment=raw.get("tax_treatment"),  # type: ignore[arg-type]
                sequence=int(str(raw.get("sequence", position))),  # type: ignore[arg-type]
            )
        )
    db.flush()
    _recalc_totals(db, estimate=est)
    db.flush()
    return est


def _require_draft(estimate: Estimate) -> None:
    if estimate.status != M.ESTIMATE_DRAFT:
        raise ConflictError("only draft estimates can be changed")


def update_estimate(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    estimate_id: uuid.UUID,
    notes: str | None = None,
    valid_until: date | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Estimate:
    est = get_estimate(db, tenant_id=tenant_id, estimate_id=estimate_id, location_ids=location_ids)
    _require_draft(est)
    if notes is not None:
        cleaned = notes.strip() or None
        if cleaned is not None and len(cleaned) > 500:
            raise ValidationError("notes must be at most 500 characters")
        est.notes = cleaned
    if valid_until is not None:
        est.valid_until = valid_until
    est.updated_at = _now()
    db.flush()
    return est


def add_estimate_line(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    estimate_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
    **fields: object,
) -> EstimateLine:
    est = get_estimate(db, tenant_id=tenant_id, estimate_id=estimate_id, location_ids=location_ids)
    _require_draft(est)
    position = len(estimate_lines(db, estimate_id=est.id)) + 1
    line = _snapshot_line(
        db,
        tenant_id=tenant_id,
        estimate_id=est.id,
        service_catalog_id=fields.get("service_catalog_id"),  # type: ignore[arg-type]
        description=fields.get("description"),  # type: ignore[arg-type]
        quantity=fields.get("quantity", 1),
        unit_rate=fields.get("unit_rate"),
        discount_amount=fields.get("discount_amount", 0),
        tax_rate=fields.get("tax_rate"),
        hsn_sac=fields.get("hsn_sac"),  # type: ignore[arg-type]
        tax_treatment=fields.get("tax_treatment"),  # type: ignore[arg-type]
        sequence=int(str(fields.get("sequence", position))),  # type: ignore[arg-type]
    )
    db.add(line)
    db.flush()
    _recalc_totals(db, estimate=est)
    est.version += 1
    db.flush()
    return line


def get_estimate_line(db: DBSession, *, tenant_id: uuid.UUID, line_id: uuid.UUID) -> EstimateLine:
    line = db.get(EstimateLine, line_id)
    if line is None or line.tenant_id != tenant_id:
        raise NotFoundError("estimate line not found")
    return line


def update_estimate_line(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    line_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
    **fields: object,
) -> EstimateLine:
    line = get_estimate_line(db, tenant_id=tenant_id, line_id=line_id)
    est = get_estimate(
        db, tenant_id=tenant_id, estimate_id=line.estimate_id, location_ids=location_ids
    )
    _require_draft(est)
    if fields.get("description") is not None:
        desc = str(fields["description"]).strip()
        if not desc or len(desc) > 300:
            raise ValidationError("line description must be 1-300 characters")
        line.description = desc
    if fields.get("hsn_sac") is not None:
        hsn = str(fields["hsn_sac"]).strip() or None
        if hsn is not None and len(hsn) > 16:
            raise ValidationError("hsn/sac must be at most 16 characters")
        line.hsn_sac = hsn
    if fields.get("tax_treatment") is not None:
        treatment = str(fields["tax_treatment"]).strip().lower()
        if treatment not in M.TAX_TREATMENTS:
            raise ValidationError("unknown tax treatment")
        line.tax_treatment = treatment
    recompute = False
    if fields.get("quantity") is not None:
        line.quantity = moneylib.ensure_decimal(fields["quantity"], field="quantity")
        if line.quantity <= 0:
            raise ValidationError("quantity must be positive")
        recompute = True
    if fields.get("unit_rate") is not None:
        line.unit_rate = moneylib.ensure_decimal(fields["unit_rate"], field="unit_rate")
        if line.unit_rate < 0:
            raise ValidationError("unit rate must be non-negative")
        recompute = True
    if fields.get("discount_amount") is not None:
        line.discount_amount = moneylib.ensure_decimal(
            fields["discount_amount"], field="discount_amount"
        )
        if line.discount_amount < 0:
            raise ValidationError("discount must be non-negative")
        recompute = True
    if fields.get("tax_rate") is not None:
        line.tax_rate = moneylib.ensure_decimal(fields["tax_rate"], field="tax_rate")
        if line.tax_rate < 0 or line.tax_rate > 100:
            raise ValidationError("tax rate must be between 0 and 100")
        recompute = True
    if fields.get("sequence") is not None:
        line.sequence = int(str(fields["sequence"]))  # type: ignore[arg-type]
    if recompute:
        computed = moneylib.compute_line_total(
            quantity=line.quantity,
            unit_rate=line.unit_rate,
            discount_amount=line.discount_amount,
            tax_rate_percent=line.tax_rate,
        )
        line.taxable_amount = computed["taxable_amount"]
        line.tax_amount = computed["tax_amount"]
        line.line_total = computed["line_total"]
    _recalc_totals(db, estimate=est)
    est.version += 1
    db.flush()
    return line


def remove_estimate_line(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    line_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Estimate:
    line = get_estimate_line(db, tenant_id=tenant_id, line_id=line_id)
    est = get_estimate(
        db, tenant_id=tenant_id, estimate_id=line.estimate_id, location_ids=location_ids
    )
    _require_draft(est)
    db.delete(line)
    db.flush()
    _recalc_totals(db, estimate=est)
    est.version += 1
    db.flush()
    return est


def transition_estimate(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    estimate_id: uuid.UUID,
    to_status: str,
    actor_id: uuid.UUID | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Estimate:
    """Single writer for estimate lifecycle. Same-state is a no-op success;
    illegal edges are conflicts. Terminal states never move."""
    if to_status not in M.ESTIMATE_STATUSES:
        raise ValidationError("unknown status")
    est = get_estimate(db, tenant_id=tenant_id, estimate_id=estimate_id, location_ids=location_ids)
    if est.status == to_status:
        return est
    if to_status not in ESTIMATE_TRANSITIONS[est.status]:
        raise ConflictError(f"cannot move estimate from {est.status} to {to_status}")
    if to_status == M.ESTIMATE_ISSUED:
        if est.valid_until is not None and est.valid_until < date.today():
            raise ValidationError("cannot issue an estimate past its valid-until date")
        _recalc_totals(db, estimate=est)
        est.issued_by = actor_id
        est.issued_at = _now()
    est.status = to_status
    est.version += 1
    est.updated_at = _now()
    db.flush()
    return est


def issue_estimate(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    estimate_id: uuid.UUID,
    actor_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Estimate:
    return transition_estimate(
        db,
        tenant_id=tenant_id,
        estimate_id=estimate_id,
        to_status=M.ESTIMATE_ISSUED,
        actor_id=actor_id,
        location_ids=location_ids,
    )


def cancel_estimate(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    estimate_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Estimate:
    return transition_estimate(
        db,
        tenant_id=tenant_id,
        estimate_id=estimate_id,
        to_status=M.ESTIMATE_CANCELLED,
        location_ids=location_ids,
    )


def expire_estimate(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    estimate_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Estimate:
    return transition_estimate(
        db,
        tenant_id=tenant_id,
        estimate_id=estimate_id,
        to_status=M.ESTIMATE_EXPIRED,
        location_ids=location_ids,
    )
