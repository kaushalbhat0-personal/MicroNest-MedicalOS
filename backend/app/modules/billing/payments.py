"""Payment service. Single authority for payment recording, explicit
manual allocation, allocation reversal, and derived payment state (P4.5).

Payment != allocation: a payment is money received; an allocation applies
it to invoices. No automatic FIFO — every allocation names its invoices
explicitly. Balances are derived from immutable rows; no mutable
`paid_amount` exists anywhere. Overpayments stay as explicit unallocated
patient credit (derived, never discarded, never a fake invoice).

P4.6 adds the refund leg: `unallocated = amount − allocated − refunded`,
and payment status gains the refund-derived layer
(`partially_refunded` / `refunded`). Refund rows themselves live in
`refunds.py`; this module owns the payment-side derivation.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.modules.billing import invoices as invoices_svc
from app.modules.billing import models as M
from app.modules.billing import money as moneylib
from app.modules.billing.models import Invoice, Payment, PaymentAllocation
from app.modules.clinical.service import get_encounter
from app.modules.clinics import service as clinics_service
from app.modules.patients import service as patients_service
from app.platform import ids
from app.platform.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.platform.time import UTC


def _now() -> datetime:
    return datetime.now(UTC)


METHOD_CASH = "cash"
METHOD_UPI = "upi"
METHOD_MANUAL_CARD = "manual_card"
METHOD_MANUAL_OTHER = "manual_other"
PAYMENT_METHODS = (METHOD_CASH, METHOD_UPI, METHOD_MANUAL_CARD, METHOD_MANUAL_OTHER)


def _normalize_method(method: str | None) -> str:
    cleaned = (method or "").strip().lower()
    if cleaned not in PAYMENT_METHODS:
        raise ValidationError(f"unknown payment method: {method}")
    return cleaned


def _lock_payment(db: DBSession, *, payment_id: uuid.UUID) -> None:
    """Serialize concurrent allocation/reversal decisions per payment
    (scheduling-service advisory-lock precedent)."""
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key)::bigint)"),
        {"key": f"bill-pay:{payment_id}"},
    )


def _lock_invoices(db: DBSession, *, invoice_ids: list[uuid.UUID]) -> None:
    """Serialize competing allocations per invoice, in deterministic order
    so concurrent multi-invoice requests cannot deadlock."""
    for invoice_id in sorted(set(invoice_ids)):
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key)::bigint)"),
            {"key": f"bill-alloc-inv:{invoice_id}"},
        )


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
            raise ValidationError("payment location must match the encounter location")
        if location_ids and enc.location_id not in location_ids:
            raise ForbiddenError("location is outside your scope")
    elif location_ids and location_id not in location_ids:
        raise ForbiddenError("location is outside your scope")


def _payment_in_scope(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    payment: Payment,
    location_ids: frozenset[uuid.UUID] | None,
) -> None:
    if not location_ids:
        return
    if payment.encounter_id is not None:
        enc = get_encounter(db, tenant_id=tenant_id, encounter_id=payment.encounter_id)
        if enc.location_id not in location_ids:
            raise ForbiddenError("location is outside your scope")
    elif payment.location_id not in location_ids:
        raise ForbiddenError("location is outside your scope")


def get_payment(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    payment_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Payment:
    payment = db.get(Payment, payment_id)
    if payment is None or payment.tenant_id != tenant_id:
        raise NotFoundError("payment not found")
    _payment_in_scope(db, tenant_id=tenant_id, payment=payment, location_ids=location_ids)
    return payment


def payment_allocations(db: DBSession, *, payment_id: uuid.UUID) -> list[PaymentAllocation]:
    return list(
        db.execute(
            select(PaymentAllocation)
            .where(PaymentAllocation.payment_id == payment_id)
            .order_by(PaymentAllocation.created_at, PaymentAllocation.id)
        )
        .scalars()
        .all()
    )


def allocations_for_invoice(db: DBSession, *, invoice_id: uuid.UUID) -> list[PaymentAllocation]:
    return list(
        db.execute(
            select(PaymentAllocation)
            .where(PaymentAllocation.invoice_id == invoice_id)
            .order_by(PaymentAllocation.created_at, PaymentAllocation.id)
        )
        .scalars()
        .all()
    )


def list_payments(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID | None = None,
    status: str | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
    limit: int = 50,
    cursor: uuid.UUID | None = None,
) -> tuple[list[Payment], uuid.UUID | None]:
    """Keyset page over (created_at, id)."""
    if status is not None and status not in M.PAYMENT_STATUSES:
        raise ValidationError("unknown status")
    q = select(Payment).where(Payment.tenant_id == tenant_id)
    if location_ids:
        q = q.where(Payment.location_id.in_(list(location_ids)))
    if patient_id is not None:
        q = q.where(Payment.patient_id == patient_id)
    if status is not None:
        q = q.where(Payment.status == status)
    if cursor is not None:
        anchor = get_payment(db, tenant_id=tenant_id, payment_id=cursor)
        q = q.where(
            (Payment.created_at > anchor.created_at)
            | ((Payment.created_at == anchor.created_at) & (Payment.id > anchor.id))
        )
    capped = min(max(limit, 1), 200)
    rows = list(
        db.execute(q.order_by(Payment.created_at, Payment.id).limit(capped + 1)).scalars().all()
    )
    if len(rows) > capped:
        return rows[:-1], rows[-2].id
    return rows, None


def allocated_for_payment(db: DBSession, *, payment: Payment) -> Decimal:
    """Derived: effective allocated total of a payment."""
    return invoices_svc.effective_allocated(db, payment_id=payment.id)


def effective_refunded(db: DBSession, *, payment_id: uuid.UUID) -> Decimal:
    """Derived refunded total: sum of ISSUED refunds against the payment.
    Single authority for the refund leg (P4-01 §14). No refund void exists
    in P4.6, so every persisted refund row counts."""
    rows = (
        db.execute(
            select(M.Refund.amount).where(
                M.Refund.payment_id == payment_id,
                M.Refund.status == M.REFUND_ISSUED,
            )
        )
        .scalars()
        .all()
    )
    return moneylib.quantize_half_up(
        sum((moneylib.ensure_decimal(v, field="amount") for v in rows), Decimal(0))
    )


def refundable_for_payment(db: DBSession, *, payment: Payment) -> Decimal:
    """Derived refundable balance (P4-01 §14): captured minus already
    refunded. Never negative by construction (refunds are capped)."""
    amount = moneylib.ensure_decimal(payment.amount, field="amount")
    refundable = moneylib.quantize_half_up(amount - effective_refunded(db, payment_id=payment.id))
    if refundable < 0:
        raise ValidationError("refunded amount exceeds payment amount")
    return refundable


def unallocated_for_payment(db: DBSession, *, payment: Payment) -> Decimal:
    """Derived patient credit remainder of one payment (P4-01 §12):
    `amount − allocated − refunded`. Never negative by construction
    (both legs are capped before insert)."""
    amount = moneylib.ensure_decimal(payment.amount, field="amount")
    remainder = moneylib.quantize_half_up(
        amount
        - allocated_for_payment(db, payment=payment)
        - effective_refunded(db, payment_id=payment.id)
    )
    if remainder < 0:
        raise ValidationError("allocated and refunded amounts exceed payment amount")
    return remainder


def refresh_payment_state(db: DBSession, *, payment: Payment) -> Payment:
    """Derived payment-state writer (P4.5 + P4.6 refund layer). Refund truth
    takes precedence: fully refunded → `refunded`, partially refunded →
    `partially_refunded`; otherwise allocation truth drives
    `recorded → partially_allocated → allocated`, with reversal moving it
    back. No client-supplied status is ever accepted."""
    amount = moneylib.ensure_decimal(payment.amount, field="amount")
    refunded = effective_refunded(db, payment_id=payment.id)
    if refunded == amount and amount > 0:
        new_status = M.PAYMENT_REFUNDED
    elif refunded > 0:
        if refunded > amount:
            raise ValidationError("refunded amount exceeds payment amount")
        new_status = M.PAYMENT_PARTIALLY_REFUNDED
    else:
        allocated = allocated_for_payment(db, payment=payment)
        if allocated == 0:
            new_status = M.PAYMENT_RECORDED
        elif allocated < amount:
            new_status = M.PAYMENT_PARTIALLY_ALLOCATED
        elif allocated == amount:
            new_status = M.PAYMENT_ALLOCATED
        else:
            raise ValidationError("allocated amount exceeds payment amount")
    if new_status != payment.status:
        payment.status = new_status
        payment.updated_at = _now()
        db.flush()
    return payment


def patient_credit(db: DBSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID) -> Decimal:
    """Derived patient-level credit (P4-01 §13): sum of unallocated payment
    remainders for (tenant, patient). No ledger table — computed, never
    stored. Existence of the patient is verified (404 oracle). The §13
    "open credit-note remainder" term is zero by construction in P4: credit
    notes exceeding the invoice outstanding are rejected at issue, so no
    credit-note remainder can ever exist — patient credit comes only from
    payment remainders and is never a credit note."""
    patients_service.get_patient(db, tenant_id=tenant_id, patient_id=patient_id)
    payments = list(
        db.execute(
            select(Payment).where(
                Payment.tenant_id == tenant_id,
                Payment.patient_id == patient_id,
            )
        )
        .scalars()
        .all()
    )
    total = sum((unallocated_for_payment(db, payment=p) for p in payments), Decimal(0))
    return moneylib.quantize_half_up(total)


def create_payment(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    patient_id: uuid.UUID,
    location_id: uuid.UUID,
    method: str,
    amount: object,
    currency: str = "INR",
    encounter_id: uuid.UUID | None = None,
    received_at: datetime | None = None,
    provider_ref: str | None = None,
    provider_data: dict[str, object] | None = None,
    idempotency_key: str | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Payment:
    """Record money received. Status starts `recorded`; allocation moves it.
    Provider facts stay opaque inside `provider_data` (never queried)."""
    moneylib.validate_currency(currency)
    _validate_refs(
        db,
        tenant_id=tenant_id,
        patient_id=patient_id,
        location_id=location_id,
        encounter_id=encounter_id,
        location_ids=location_ids,
    )
    normalized_method = _normalize_method(method)
    value = moneylib.ensure_decimal(amount, field="amount")
    if value <= 0:
        raise ValidationError("payment amount must be positive")
    received = received_at or _now()
    ref = (provider_ref or "").strip() or None
    if ref is not None and (len(ref) < 2 or len(ref) > 128):
        raise ValidationError("provider reference must be 2-128 characters")
    key = (idempotency_key or "").strip() or None
    if key:
        existing = db.execute(
            select(Payment).where(
                Payment.tenant_id == tenant_id,
                Payment.idempotency_key == key,
            )
        ).scalar_one_or_none()
        if existing is not None:
            if (
                existing.patient_id != patient_id
                or existing.location_id != location_id
                or existing.method != normalized_method
                or moneylib.ensure_decimal(existing.amount, field="amount") != value
            ):
                raise ConflictError("idempotency key was used for a different payment")
            return existing
    now = _now()
    payment = Payment(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        location_id=location_id,
        patient_id=patient_id,
        encounter_id=encounter_id,
        status=M.PAYMENT_RECORDED,
        amount=value,
        currency=currency,
        method=normalized_method,
        received_at=received,
        provider_ref=ref,
        provider_data=dict(provider_data) if provider_data is not None else None,
        idempotency_key=key,
        created_by=actor_id,
        created_at=now,
        updated_at=now,
    )
    db.add(payment)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ConflictError("idempotency key was used for a different payment") from None
    return payment


def _request_matches(rows: list[PaymentAllocation], wanted: set[tuple[uuid.UUID, Decimal]]) -> bool:
    have = {
        (row.invoice_id, moneylib.ensure_decimal(row.amount, field="amount"))
        for row in rows
        if row.reversal_of_id is None
    }
    return have == wanted


def allocate_payment(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    payment_id: uuid.UUID,
    actor_id: uuid.UUID,
    items: list[dict[str, object]],
    idempotency_key: str | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> tuple[Payment, list[PaymentAllocation]]:
    """Explicit manual allocation of one payment across named invoices. No
    FIFO, no heuristics: every (invoice, amount) pair is validated against
    the payment remainder and the invoice outstanding under the payment +
    invoice advisory locks, then persisted with refreshed derived states —
    atomically. Excess stays as unallocated patient credit; it is never
    forced onto an invoice."""
    _lock_payment(db, payment_id=payment_id)
    payment = get_payment(db, tenant_id=tenant_id, payment_id=payment_id, location_ids=location_ids)
    if not items:
        raise ValidationError("allocation requires at least one invoice")
    wanted_invoices = [row["invoice_id"] for row in items]
    if len(set(wanted_invoices)) != len(wanted_invoices):
        raise ValidationError("duplicate invoice in allocation request")
    wanted: dict[uuid.UUID, Decimal] = {}
    for item in items:
        invoice_id = item["invoice_id"]
        if not isinstance(invoice_id, uuid.UUID):
            raise ValidationError("invoice_id must be a UUID")
        amount = moneylib.ensure_decimal(item.get("amount"), field="amount")
        if amount <= 0:
            raise ValidationError("allocation amount must be positive")
        wanted[invoice_id] = moneylib.quantize_half_up(amount)
    key = (idempotency_key or "").strip() or None
    if key:
        prior = [
            row
            for row in payment_allocations(db, payment_id=payment.id)
            if row.idempotency_key == key
        ]
        if prior:
            if not _request_matches(prior, set(wanted.items())):
                raise ConflictError("idempotency key was used for a different allocation")
            return payment, prior
    _lock_invoices(db, invoice_ids=list(wanted))
    invoices: dict[uuid.UUID, Invoice] = {}
    for invoice_id in wanted:
        invoice = invoices_svc.get_invoice(
            db, tenant_id=tenant_id, invoice_id=invoice_id, location_ids=location_ids
        )
        if invoice.patient_id != payment.patient_id:
            raise ValidationError("payment and invoice belong to different patients")
        if invoice.status not in (M.INVOICE_ISSUED, M.INVOICE_PARTIALLY_PAID):
            raise ConflictError(
                f"invoice {invoice_id} is not open for allocation ({invoice.status})"
            )
        invoices[invoice_id] = invoice
    created: list[PaymentAllocation] = []
    for invoice_id, amount in wanted.items():
        # Autoflush is ON: rows added earlier in this same request are
        # visible to the remainder query, so no manual bookkeeping.
        remainder = unallocated_for_payment(db, payment=payment)
        if amount > remainder:
            raise ConflictError("allocation exceeds the payment's unallocated amount")
        outstanding = invoices_svc.outstanding_for_invoice(db, invoice=invoices[invoice_id])
        if amount > outstanding:
            raise ConflictError("allocation exceeds the invoice outstanding amount")
        row = PaymentAllocation(
            id=ids.uuid7(),
            tenant_id=tenant_id,
            patient_id=payment.patient_id,
            payment_id=payment.id,
            invoice_id=invoice_id,
            amount=amount,
            created_by=actor_id,
            idempotency_key=key,
            created_at=_now(),
        )
        db.add(row)
        created.append(row)
    db.flush()
    refresh_payment_state(db, payment=payment)
    for invoice in invoices.values():
        invoices_svc.refresh_invoice_payment_state(db, invoice=invoice)
    db.flush()
    return payment, created


def reverse_allocation(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    allocation_id: uuid.UUID,
    actor_id: uuid.UUID,
    reason: str,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> PaymentAllocation:
    """Cancel one forward allocation with an explicit reversing row. The
    original row is preserved; effective balances drop by its amount and
    derived payment/invoice states follow. One reversal per allocation
    (DB-guarded); reversal rows and already-reversed rows cannot be
    reversed again. Refunds (money returned) remain P4.6."""
    cleaned = (reason or "").strip()
    if len(cleaned) < 2 or len(cleaned) > 200:
        raise ValidationError("reversal reason must be 2-200 characters")
    original = db.get(PaymentAllocation, allocation_id)
    if original is None or original.tenant_id != tenant_id:
        raise NotFoundError("allocation not found")
    if original.reversal_of_id is not None:
        raise ConflictError("reversal rows cannot be reversed")
    _lock_payment(db, payment_id=original.payment_id)
    _lock_invoices(db, invoice_ids=[original.invoice_id])
    payment = get_payment(
        db, tenant_id=tenant_id, payment_id=original.payment_id, location_ids=location_ids
    )
    invoice = invoices_svc.get_invoice(
        db, tenant_id=tenant_id, invoice_id=original.invoice_id, location_ids=location_ids
    )
    existing = db.execute(
        select(PaymentAllocation.id).where(PaymentAllocation.reversal_of_id == original.id)
    ).first()
    if existing is not None:
        raise ConflictError("allocation has already been reversed")
    reversal = PaymentAllocation(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        patient_id=original.patient_id,
        payment_id=original.payment_id,
        invoice_id=original.invoice_id,
        amount=moneylib.ensure_decimal(original.amount, field="amount"),
        reversal_of_id=original.id,
        created_by=actor_id,
        created_at=_now(),
    )
    db.add(reversal)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ConflictError("allocation has already been reversed") from None
    refresh_payment_state(db, payment=payment)
    invoices_svc.refresh_invoice_payment_state(db, invoice=invoice)
    db.flush()
    return reversal
