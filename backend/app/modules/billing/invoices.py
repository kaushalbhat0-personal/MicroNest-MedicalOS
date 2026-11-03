"""Invoice service. Single authority for the invoice lifecycle.

DRAFT creation/editing, ISSUE with series numbering, VOID under the
pre-payment rule, and estimate→invoice snapshot conversion live here,
plus the single authority for invoice payment balances (P4.5): effective
allocated totals derived from allocation rows (forward minus reversed)
and the derived payment-state refresh, driven only by allocation truth.

Invoices are financial truth once issued: lines, totals, patient,
location, source estimate, currency, tax snapshots, and numbering
freeze. Corrections flow through adjustment documents (refund / credit
note, P4.6), never through UPDATEs of issued rows. Conversion copies
estimate values into independent snapshots; later catalog, estimate, or
treatment-plan edits never touch the invoice.

P4.6 note on status vs balance: invoice STATUS follows allocation truth
only (P4-01 §8 — credit notes "reduce outstanding without state rewrite
beyond balance"). The collectible OUTSTANDING subtracts both effective
allocations and issued credit notes.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.modules.billing import estimates as estimates_svc
from app.modules.billing import models as M
from app.modules.billing import money as moneylib
from app.modules.billing import numbering as numberinglib
from app.modules.billing import service_catalog as catalog_svc
from app.modules.billing.models import EstimateLine, Invoice, InvoiceLine
from app.modules.clinical.service import get_encounter
from app.modules.clinics import service as clinics_service
from app.modules.patients import service as patients_service
from app.platform import ids
from app.platform.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.platform.time import UTC


def _now() -> datetime:
    return datetime.now(UTC)


INVOICE_TRANSITIONS: dict[str, frozenset[str]] = {
    M.INVOICE_DRAFT: frozenset({M.INVOICE_ISSUED, M.INVOICE_VOIDED}),
    # Payment-driven states move ONLY through refresh_invoice_payment_state
    # (allocation truth, P4.5) — never through the generic transition writer,
    # so no API can move them arbitrarily. The map stays terminal here by
    # design; see _DERIVED_PAYMENT_MOVES below.
    M.INVOICE_ISSUED: frozenset({M.INVOICE_VOIDED}),
    M.INVOICE_PARTIALLY_PAID: frozenset(),
    M.INVOICE_PAID: frozenset(),
    M.INVOICE_VOIDED: frozenset(),
}

# The only legal derived payment-state moves. Forward moves follow
# allocation; backward moves happen only when a reversal removes the
# allocation truth that promoted the invoice.
_DERIVED_PAYMENT_MOVES: frozenset[tuple[str, str]] = frozenset(
    {
        (M.INVOICE_ISSUED, M.INVOICE_PARTIALLY_PAID),
        (M.INVOICE_ISSUED, M.INVOICE_PAID),
        (M.INVOICE_PARTIALLY_PAID, M.INVOICE_PAID),
        (M.INVOICE_PARTIALLY_PAID, M.INVOICE_ISSUED),
        (M.INVOICE_PAID, M.INVOICE_PARTIALLY_PAID),
        (M.INVOICE_PAID, M.INVOICE_ISSUED),
    }
)


def _lock_conversion(db: DBSession, *, estimate_id: uuid.UUID) -> None:
    """Serialize concurrent conversions of the same estimate for this
    transaction (scheduling-service advisory-lock precedent). Check-then-
    insert becomes atomic per estimate under READ COMMITTED."""
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key)::bigint)"),
        {"key": f"bill-conv:{estimate_id}"},
    )


def _lock_series(
    db: DBSession, *, tenant_id: uuid.UUID, location_id: uuid.UUID, financial_year: str
) -> None:
    """Serialize number allocation per (tenant, location, FY) series."""
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key)::bigint)"),
        {"key": f"bill-inv-series:{tenant_id}:{location_id}:{financial_year}"},
    )


def _invoice_in_scope(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    invoice: Invoice,
    location_ids: frozenset[uuid.UUID] | None,
) -> None:
    """Fail-closed location scope (estimate-service pattern)."""
    if not location_ids:
        return
    if invoice.encounter_id is not None:
        enc = get_encounter(db, tenant_id=tenant_id, encounter_id=invoice.encounter_id)
        if enc.location_id not in location_ids:
            raise ForbiddenError("location is outside your scope")
    elif invoice.location_id not in location_ids:
        raise ForbiddenError("location is outside your scope")


def _validate_refs(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    location_id: uuid.UUID,
    encounter_id: uuid.UUID | None,
    location_ids: frozenset[uuid.UUID] | None,
) -> None:
    patient = patients_service.get_patient(db, tenant_id=tenant_id, patient_id=patient_id)
    if not patient.is_active:
        raise ValidationError("patient is not active")
    location = clinics_service.get_location(db, tenant_id=tenant_id, location_id=location_id)
    if not location.is_active:
        raise ValidationError("location is not active")
    if encounter_id is not None:
        enc = get_encounter(db, tenant_id=tenant_id, encounter_id=encounter_id)
        if enc.patient_id != patient_id:
            raise ValidationError("encounter does not belong to this patient")
        if enc.location_id != location_id:
            raise ValidationError("invoice location must match the encounter location")
        if location_ids and enc.location_id not in location_ids:
            raise ForbiddenError("location is outside your scope")
    elif location_ids and location_id not in location_ids:
        raise ForbiddenError("location is outside your scope")


def get_invoice(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    invoice_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Invoice:
    inv = db.get(Invoice, invoice_id)
    if inv is None or inv.tenant_id != tenant_id:
        raise NotFoundError("invoice not found")
    _invoice_in_scope(db, tenant_id=tenant_id, invoice=inv, location_ids=location_ids)
    return inv


def invoice_lines(db: DBSession, *, invoice_id: uuid.UUID) -> list[InvoiceLine]:
    return list(
        db.execute(
            select(InvoiceLine)
            .where(InvoiceLine.invoice_id == invoice_id)
            .order_by(InvoiceLine.sequence, InvoiceLine.id)
        )
        .scalars()
        .all()
    )


def list_invoices(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID | None = None,
    status: str | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
    limit: int = 50,
    cursor: uuid.UUID | None = None,
) -> tuple[list[Invoice], uuid.UUID | None]:
    """Keyset page over (created_at, id). Location filter pins the invoice's
    own location (creation forces equality with any linked encounter)."""
    if status is not None and status not in M.INVOICE_STATUSES:
        raise ValidationError("unknown status")
    q = select(Invoice).where(Invoice.tenant_id == tenant_id)
    if location_ids:
        q = q.where(Invoice.location_id.in_(list(location_ids)))
    if patient_id is not None:
        q = q.where(Invoice.patient_id == patient_id)
    if status is not None:
        q = q.where(Invoice.status == status)
    if cursor is not None:
        anchor = get_invoice(db, tenant_id=tenant_id, invoice_id=cursor)
        q = q.where(
            (Invoice.created_at > anchor.created_at)
            | ((Invoice.created_at == anchor.created_at) & (Invoice.id > anchor.id))
        )
    capped = min(max(limit, 1), 200)
    rows = list(
        db.execute(q.order_by(Invoice.created_at, Invoice.id).limit(capped + 1)).scalars().all()
    )
    if len(rows) > capped:
        return rows[:-1], rows[-2].id
    return rows, None


def _snapshot_direct_line(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    invoice_id: uuid.UUID,
    service_catalog_id: uuid.UUID | None,
    description: str | None,
    quantity: object,
    unit_rate: object | None,
    discount_amount: object,
    tax_rate: object | None,
    hsn_sac: str | None,
    tax_treatment: str | None,
    sequence: int,
) -> InvoiceLine:
    """Snapshot caller/catalog values into an independent line. The catalog
    id (when given) only fills defaults — it is never stored, so later
    catalog edits can never rewrite this row."""
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
    return InvoiceLine(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        invoice_id=invoice_id,
        source_estimate_line_id=None,
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
        created_at=_now(),
    )


def _recalc_totals(db: DBSession, *, invoice: Invoice) -> None:
    lines = invoice_lines(db, invoice_id=invoice.id)
    subtotal = sum((moneylib.ensure_decimal(line.taxable_amount) for line in lines), Decimal(0))
    tax_total = sum((moneylib.ensure_decimal(line.tax_amount) for line in lines), Decimal(0))
    invoice.subtotal = moneylib.quantize_half_up(subtotal)
    invoice.tax_total = moneylib.quantize_half_up(tax_total)
    invoice.grand_total = moneylib.compute_invoice_total([line.line_total for line in lines])
    invoice.updated_at = _now()


def create_invoice(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    patient_id: uuid.UUID,
    location_id: uuid.UUID,
    encounter_id: uuid.UUID | None = None,
    due_date: date | None = None,
    notes: str | None = None,
    currency: str = "INR",
    items: list[dict[str, object]] | None = None,
    idempotency_key: str | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Invoice:
    """Direct invoice creation (OTC / standalone per P4-01 §18). Draft only;
    numbering is allocated at issue, never here."""
    moneylib.validate_currency(currency)
    _validate_refs(
        db,
        tenant_id=tenant_id,
        patient_id=patient_id,
        location_id=location_id,
        encounter_id=encounter_id,
        location_ids=location_ids,
    )
    key = (idempotency_key or "").strip() or None
    if key:
        existing = db.execute(
            select(Invoice).where(
                Invoice.tenant_id == tenant_id,
                Invoice.idempotency_key == key,
            )
        ).scalar_one_or_none()
        if existing is not None:
            if existing.patient_id != patient_id or existing.location_id != location_id:
                raise ConflictError("idempotency key was used for a different invoice")
            return existing
    now = _now()
    inv = Invoice(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        location_id=location_id,
        patient_id=patient_id,
        encounter_id=encounter_id,
        source_estimate_id=None,
        status=M.INVOICE_DRAFT,
        version=1,
        currency=currency,
        due_date=due_date,
        notes=(notes or "").strip() or None,
        idempotency_key=key,
        created_by=actor_id,
        created_at=now,
        updated_at=now,
    )
    if inv.notes is not None and len(inv.notes) > 500:
        raise ValidationError("notes must be at most 500 characters")
    db.add(inv)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ConflictError("idempotency key was used for a different invoice") from None
    for position, raw in enumerate(items or [], start=1):
        db.add(
            _snapshot_direct_line(
                db,
                tenant_id=tenant_id,
                invoice_id=inv.id,
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
    _recalc_totals(db, invoice=inv)
    db.flush()
    return inv


def _require_draft(invoice: Invoice) -> None:
    if invoice.status != M.INVOICE_DRAFT:
        raise ConflictError("only draft invoices can be changed")


def update_invoice(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    invoice_id: uuid.UUID,
    notes: str | None = None,
    due_date: date | None = None,
    clear_due_date: bool = False,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Invoice:
    """Draft metadata edit. Patient, location, source, and currency are
    identity — they are never accepted here, before or after issue."""
    inv = get_invoice(db, tenant_id=tenant_id, invoice_id=invoice_id, location_ids=location_ids)
    _require_draft(inv)
    if notes is not None:
        cleaned = notes.strip() or None
        if cleaned is not None and len(cleaned) > 500:
            raise ValidationError("notes must be at most 500 characters")
        inv.notes = cleaned
    if clear_due_date:
        inv.due_date = None
    elif due_date is not None:
        inv.due_date = due_date
    inv.updated_at = _now()
    db.flush()
    return inv


def add_invoice_line(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    invoice_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
    **fields: object,
) -> InvoiceLine:
    inv = get_invoice(db, tenant_id=tenant_id, invoice_id=invoice_id, location_ids=location_ids)
    _require_draft(inv)
    position = len(invoice_lines(db, invoice_id=inv.id)) + 1
    line = _snapshot_direct_line(
        db,
        tenant_id=tenant_id,
        invoice_id=inv.id,
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
    _recalc_totals(db, invoice=inv)
    inv.version += 1
    db.flush()
    return line


def get_invoice_line(db: DBSession, *, tenant_id: uuid.UUID, line_id: uuid.UUID) -> InvoiceLine:
    line = db.get(InvoiceLine, line_id)
    if line is None or line.tenant_id != tenant_id:
        raise NotFoundError("invoice line not found")
    return line


def update_invoice_line(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    line_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
    **fields: object,
) -> InvoiceLine:
    line = get_invoice_line(db, tenant_id=tenant_id, line_id=line_id)
    inv = get_invoice(
        db, tenant_id=tenant_id, invoice_id=line.invoice_id, location_ids=location_ids
    )
    _require_draft(inv)
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
    _recalc_totals(db, invoice=inv)
    inv.version += 1
    db.flush()
    return line


def remove_invoice_line(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    line_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Invoice:
    line = get_invoice_line(db, tenant_id=tenant_id, line_id=line_id)
    inv = get_invoice(
        db, tenant_id=tenant_id, invoice_id=line.invoice_id, location_ids=location_ids
    )
    _require_draft(inv)
    db.delete(line)
    db.flush()
    _recalc_totals(db, invoice=inv)
    inv.version += 1
    db.flush()
    return inv


def _allocate_doc_number(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID,
    financial_year: str,
) -> int:
    """Next integer in the (tenant, location, FY) invoice series. Gaps on
    rollback are accepted; duplicates are rejected by the per-series
    UNIQUE constraint."""
    _lock_series(db, tenant_id=tenant_id, location_id=location_id, financial_year=financial_year)
    current = db.execute(
        text(
            "SELECT COALESCE(MAX(doc_number), 0) FROM invoices "
            "WHERE tenant_id = :t AND location_id = :l AND financial_year = :fy"
        ),
        {"t": str(tenant_id), "l": str(location_id), "fy": financial_year},
    ).scalar_one()
    return int(current) + 1


def transition_invoice(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    invoice_id: uuid.UUID,
    to_status: str,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Invoice:
    """Single writer for the draft/issue/void invoice edges. Same-state is
    a no-op success; illegal edges are conflicts. Terminal states never
    move. Payment-driven edges move only through
    refresh_invoice_payment_state (allocation truth), never here — no API
    exposes arbitrary transitions."""
    if to_status not in M.INVOICE_STATUSES:
        raise ValidationError("unknown status")
    inv = get_invoice(db, tenant_id=tenant_id, invoice_id=invoice_id, location_ids=location_ids)
    if inv.status == to_status:
        return inv
    if to_status not in INVOICE_TRANSITIONS[inv.status]:
        raise ConflictError(f"cannot move invoice from {inv.status} to {to_status}")
    inv.status = to_status
    inv.version += 1
    inv.updated_at = _now()
    db.flush()
    return inv


def issue_invoice(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    invoice_id: uuid.UUID,
    actor_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Invoice:
    """Issue a draft: validate, freeze totals, allocate the series number,
    stamp issue metadata — atomically. Re-issuing an issued invoice is a
    no-op success that never reallocates the number."""
    inv = get_invoice(db, tenant_id=tenant_id, invoice_id=invoice_id, location_ids=location_ids)
    if inv.status == M.INVOICE_ISSUED:
        return inv
    if inv.status != M.INVOICE_DRAFT:
        raise ConflictError(f"cannot issue invoice from status {inv.status}")
    lines = invoice_lines(db, invoice_id=inv.id)
    if not lines:
        raise ValidationError("cannot issue an invoice with no lines")
    moneylib.validate_currency(inv.currency)
    _recalc_totals(db, invoice=inv)
    fy = numberinglib.fy_for(_now())
    numberinglib.validate_fy(fy)
    inv.financial_year = fy
    inv.doc_number = _allocate_doc_number(
        db, tenant_id=inv.tenant_id, location_id=inv.location_id, financial_year=fy
    )
    inv.issued_by = actor_id
    inv.issued_at = _now()
    inv.status = M.INVOICE_ISSUED
    inv.version += 1
    inv.updated_at = _now()
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ConflictError("numbering conflict, retry the issue") from None
    return inv


def _assert_no_settlement(db: DBSession, *, invoice_id: uuid.UUID) -> None:
    """Pre-payment void rule: zero *effective* allocations and zero credit
    notes. Reversed allocations cancel out — a fully reversed invoice is
    voidable again; any live settlement row blocks the void."""
    if effective_allocated(db, invoice_id=invoice_id) > 0:
        raise ConflictError("invoice has allocations and cannot be voided")
    note = db.execute(
        select(M.CreditNote.id).where(M.CreditNote.invoice_id == invoice_id).limit(1)
    ).first()
    if note is not None:
        raise ConflictError("invoice has credit notes and cannot be voided")


def void_invoice(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    invoice_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
    reason: str | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Invoice:
    """Void a draft (simple cancellation) or an unsettled issued invoice.
    Issued invoices with live allocations cannot be voided — reverse the
    allocations first (P4.5) or correct via refund / credit note (P4.6+)."""
    inv = get_invoice(db, tenant_id=tenant_id, invoice_id=invoice_id, location_ids=location_ids)
    if inv.status == M.INVOICE_VOIDED:
        return inv
    cleaned = (reason or "").strip() or None
    if inv.status == M.INVOICE_DRAFT:
        if cleaned is not None and len(cleaned) > 200:
            raise ValidationError("void reason must be at most 200 characters")
    elif inv.status == M.INVOICE_ISSUED:
        if cleaned is None or len(cleaned) < 2 or len(cleaned) > 200:
            raise ValidationError("void reason must be 2-200 characters")
        _assert_no_settlement(db, invoice_id=inv.id)
    else:
        raise ConflictError(f"cannot void invoice from status {inv.status}")
    inv.status = M.INVOICE_VOIDED
    inv.void_reason = cleaned
    inv.voided_by = actor_id
    inv.voided_at = _now()
    inv.version += 1
    inv.updated_at = _now()
    db.flush()
    return inv


def effective_allocated(
    db: DBSession,
    *,
    invoice_id: uuid.UUID | None = None,
    payment_id: uuid.UUID | None = None,
) -> Decimal:
    """Single authority for allocation truth. Effective total = forward
    allocation rows minus forward rows cancelled by a reversing row
    (at most one reversal per row, enforced by `uq_alloc_reversal_once`).
    Exactly one of invoice_id / payment_id must be given."""
    if (invoice_id is None) == (payment_id is None):
        raise ValidationError("exactly one of invoice_id or payment_id is required")
    filt = (
        M.PaymentAllocation.invoice_id == invoice_id
        if invoice_id is not None
        else M.PaymentAllocation.payment_id == payment_id
    )
    rows = db.execute(
        select(
            M.PaymentAllocation.id,
            M.PaymentAllocation.amount,
            M.PaymentAllocation.reversal_of_id,
        ).where(filt)
    ).all()
    forward: dict[uuid.UUID, Decimal] = {}
    cancelled: set[uuid.UUID] = set()
    for row_id, amount, reversal_of in rows:
        if reversal_of is None:
            forward[row_id] = moneylib.ensure_decimal(amount, field="amount")
        else:
            cancelled.add(reversal_of)
    total = sum(
        (amount for row_id, amount in forward.items() if row_id not in cancelled),
        Decimal(0),
    )
    return moneylib.quantize_half_up(total)


def credited_for_invoice(db: DBSession, *, invoice_id: uuid.UUID) -> Decimal:
    """Derived credited total: sum of ISSUED credit notes against the
    invoice. Draft notes are unnumbered proposals and affect no balance;
    issued notes are immutable so the sum only grows. Single authority for
    the credit leg of the invoice balance."""
    total = (
        db.execute(
            select(M.CreditNote.amount).where(
                M.CreditNote.invoice_id == invoice_id,
                M.CreditNote.status == M.CREDIT_ISSUED,
            )
        )
        .scalars()
        .all()
    )
    return moneylib.quantize_half_up(
        sum((moneylib.ensure_decimal(v, field="amount") for v in total), Decimal(0))
    )


def outstanding_for_invoice(db: DBSession, *, invoice: Invoice) -> Decimal:
    """Derived collectible balance (P4-01 §12): grand total minus effective
    allocations minus issued credit notes. Never negative by construction
    (both legs are capped before insert)."""
    total = moneylib.ensure_decimal(invoice.grand_total, field="grand_total")
    outstanding = moneylib.quantize_half_up(
        total
        - effective_allocated(db, invoice_id=invoice.id)
        - credited_for_invoice(db, invoice_id=invoice.id)
    )
    if outstanding < 0:
        raise ValidationError("allocated and credited amounts exceed invoice total")
    return outstanding


def refresh_invoice_payment_state(db: DBSession, *, invoice: Invoice) -> Invoice:
    """Derived payment-state writer (P4.5). The ONLY mover of the
    `issued ↔ partially_paid ↔ paid` edges: state follows allocation
    truth after every allocate/reverse. Drafts and voided invoices are
    never touched here; backward moves happen only when a reversal
    removes the allocation truth that promoted the invoice."""
    if invoice.status not in (
        M.INVOICE_ISSUED,
        M.INVOICE_PARTIALLY_PAID,
        M.INVOICE_PAID,
    ):
        return invoice
    allocated = effective_allocated(db, invoice_id=invoice.id)
    total = moneylib.ensure_decimal(invoice.grand_total, field="grand_total")
    if allocated == 0:
        new_status = M.INVOICE_ISSUED
    elif allocated < total:
        new_status = M.INVOICE_PARTIALLY_PAID
    elif allocated == total:
        new_status = M.INVOICE_PAID
    else:
        raise ValidationError("allocated amount exceeds invoice total")
    if new_status != invoice.status:
        if (invoice.status, new_status) not in _DERIVED_PAYMENT_MOVES:
            raise ConflictError(f"cannot move invoice from {invoice.status} to {new_status}")
        invoice.status = new_status
        invoice.version += 1
        invoice.updated_at = _now()
        db.flush()
    return invoice


def _conversion_matches(
    db: DBSession, *, invoice: Invoice, estimate_id: uuid.UUID, wanted: set[uuid.UUID]
) -> bool:
    if invoice.source_estimate_id != estimate_id:
        return False
    have = {
        line.source_estimate_line_id
        for line in invoice_lines(db, invoice_id=invoice.id)
        if line.source_estimate_line_id is not None
    }
    return have == wanted


def convert_estimate_to_invoice(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    estimate_id: uuid.UUID,
    actor_id: uuid.UUID,
    line_ids: list[uuid.UUID] | None = None,
    notes: str | None = None,
    due_date: date | None = None,
    idempotency_key: str | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Invoice:
    """Snapshot-copy selected estimate lines into a new draft invoice.

    Either the invoice + lines + estimate transition all persist, or none
    do (single session transaction — no partial financial document). Full
    conversion (every line) moves the estimate `issued → converted` through
    the P4.3 writer; partial conversion leaves it `issued`. The invoice
    holds independent snapshots: later catalog/estimate edits never touch
    it, enforced by the at-most-once index on converted lines.
    """
    _lock_conversion(db, estimate_id=estimate_id)
    est = estimates_svc.get_estimate(
        db, tenant_id=tenant_id, estimate_id=estimate_id, location_ids=location_ids
    )
    if est.status not in (M.ESTIMATE_ISSUED, M.ESTIMATE_CONVERTED):
        raise ConflictError("only issued estimates can be converted")
    all_lines = estimates_svc.estimate_lines(db, estimate_id=est.id)
    if not all_lines:
        raise ValidationError("estimate has no lines to convert")
    by_id = {line.id: line for line in all_lines}
    if line_ids is None:
        selected = list(all_lines)
    else:
        if not line_ids or len(set(line_ids)) != len(line_ids):
            raise ValidationError("conversion requires a non-empty list of unique lines")
        selected = []
        for lid in line_ids:
            line = db.get(EstimateLine, lid)
            if line is None or line.tenant_id != tenant_id:
                raise NotFoundError("estimate line not found")
            if line.estimate_id != est.id:
                raise ValidationError("estimate line does not belong to this estimate")
            selected.append(by_id.get(line.id) or line)
    wanted = {line.id for line in selected}
    key = (idempotency_key or "").strip() or None
    if key:
        existing = db.execute(
            select(Invoice).where(
                Invoice.tenant_id == tenant_id,
                Invoice.idempotency_key == key,
            )
        ).scalar_one_or_none()
        if existing is not None:
            if not _conversion_matches(db, invoice=existing, estimate_id=est.id, wanted=wanted):
                raise ConflictError("idempotency key was used for a different conversion")
            return existing
    already = set(
        db.execute(
            select(InvoiceLine.source_estimate_line_id).where(
                InvoiceLine.source_estimate_line_id.in_(list(wanted))
            )
        )
        .scalars()
        .all()
    )
    if already:
        raise ConflictError("estimate line has already been converted")
    moneylib.validate_currency(est.currency)
    now = _now()
    inv = Invoice(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        location_id=est.location_id,
        patient_id=est.patient_id,
        encounter_id=est.encounter_id,
        source_estimate_id=est.id,
        status=M.INVOICE_DRAFT,
        version=1,
        currency=est.currency,
        due_date=due_date,
        notes=(notes or "").strip() or None,
        idempotency_key=key,
        created_by=actor_id,
        created_at=now,
        updated_at=now,
    )
    if inv.notes is not None and len(inv.notes) > 500:
        raise ValidationError("notes must be at most 500 characters")
    db.add(inv)
    try:
        db.flush()
        for src in sorted(selected, key=lambda line: (line.sequence, str(line.id))):
            db.add(
                InvoiceLine(
                    id=ids.uuid7(),
                    tenant_id=tenant_id,
                    invoice_id=inv.id,
                    source_estimate_line_id=src.id,
                    description=src.description,
                    quantity=src.quantity,
                    unit_rate=src.unit_rate,
                    discount_amount=src.discount_amount,
                    taxable_amount=src.taxable_amount,
                    tax_rate=src.tax_rate,
                    tax_amount=src.tax_amount,
                    hsn_sac=src.hsn_sac,
                    tax_treatment=src.tax_treatment,
                    line_total=src.line_total,
                    sequence=src.sequence,
                    created_at=_now(),
                )
            )
        db.flush()
    except IntegrityError:
        db.rollback()
        if key:
            retry = db.execute(
                select(Invoice).where(
                    Invoice.tenant_id == tenant_id,
                    Invoice.idempotency_key == key,
                )
            ).scalar_one_or_none()
            if retry is not None and _conversion_matches(
                db, invoice=retry, estimate_id=estimate_id, wanted=wanted
            ):
                return retry
        raise ConflictError("conversion conflict: line already converted or key reused") from None
    _recalc_totals(db, invoice=inv)
    db.flush()
    converted = set(
        db.execute(
            select(InvoiceLine.source_estimate_line_id)
            .join(Invoice, InvoiceLine.invoice_id == Invoice.id)
            .where(
                Invoice.source_estimate_id == est.id,
                InvoiceLine.source_estimate_line_id.is_not(None),
            )
        )
        .scalars()
        .all()
    )
    if {line.id for line in all_lines} <= set(converted):
        estimates_svc.transition_estimate(
            db,
            tenant_id=tenant_id,
            estimate_id=est.id,
            to_status=M.ESTIMATE_CONVERTED,
            location_ids=location_ids,
        )
    return inv
