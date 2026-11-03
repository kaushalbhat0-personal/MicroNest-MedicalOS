"""Refund service (P4.6). Single authority for money returned against a
recorded payment.

A refund never mutates the payment (no `amount -= refund`, ever). Derived
facts: `refunded = sum(issued refunds)` and `refundable = captured −
refunded` (both owned by `payments.py`). Per P4-01 §14 a refund reverses
the affected allocations FIRST (explicit reversing rows through the P4.5
mechanism), then records the refund — so a fully refunded payment leaves
its invoice(s) at the allocation truth (e.g. back to `issued`), while the
money-return itself tracks on the payment, never by editing the invoice.

Reversal order is deterministic recency (newest allocation first), which
minimizes disturbance to older settled rows; an invoice-linked refund
scopes reversal to that invoice. If reversal frees more than the refund
amount, the excess is re-allocated to the last-touched invoice as a new
explicit forward row — exactly the refund amount moves, nothing more.
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
from app.modules.billing import payments as payments_svc
from app.modules.billing.models import PaymentAllocation, Refund
from app.platform import ids
from app.platform.errors import ConflictError, NotFoundError, ValidationError
from app.platform.time import UTC


def _now() -> datetime:
    return datetime.now(UTC)


def _lock_payment(db: DBSession, *, payment_id: uuid.UUID) -> None:
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key)::bigint)"),
        {"key": f"bill-pay:{payment_id}"},
    )


def get_refund(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    refund_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Refund:
    refund = db.get(Refund, refund_id)
    if refund is None or refund.tenant_id != tenant_id:
        raise NotFoundError("refund not found")
    if location_ids:
        # Scope follows the payment leg (server-verified, fail-closed).
        payments_svc.get_payment(
            db,
            tenant_id=tenant_id,
            payment_id=refund.payment_id,
            location_ids=location_ids,
        )
    return refund


def refunds_for_payment(db: DBSession, *, payment_id: uuid.UUID) -> list[Refund]:
    return list(
        db.execute(
            select(Refund)
            .where(Refund.payment_id == payment_id)
            .order_by(Refund.created_at, Refund.id)
        )
        .scalars()
        .all()
    )


def _forward_rows_newest_first(
    db: DBSession, *, payment_id: uuid.UUID, invoice_id: uuid.UUID | None = None
) -> list[PaymentAllocation]:
    """Effective forward allocation rows, newest first, optionally scoped
    to one invoice. Deterministic order (created_at, id)."""
    q = select(PaymentAllocation).where(PaymentAllocation.payment_id == payment_id)
    if invoice_id is not None:
        q = q.where(PaymentAllocation.invoice_id == invoice_id)
    rows = list(
        db.execute(q.order_by(PaymentAllocation.created_at.desc(), PaymentAllocation.id.desc()))
        .scalars()
        .all()
    )
    cancelled = {r.reversal_of_id for r in rows if r.reversal_of_id is not None}
    return [r for r in rows if r.reversal_of_id is None and r.id not in cancelled]


def _refund_matches(
    refund: Refund,
    *,
    payment_id: uuid.UUID,
    invoice_id: uuid.UUID | None,
    amount: Decimal,
) -> bool:
    return (
        refund.payment_id == payment_id
        and refund.invoice_id == invoice_id
        and moneylib.ensure_decimal(refund.amount, field="amount") == amount
    )


def create_refund(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    payment_id: uuid.UUID,
    actor_id: uuid.UUID,
    amount: object,
    reason: str,
    invoice_id: uuid.UUID | None = None,
    idempotency_key: str | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Refund:
    """Record money returned against a payment. Reverses affected
    allocations first (P4.5 reversing rows), re-allocates any reversal
    excess, then inserts the immutable refund row — atomically. The
    payment row itself is never mutated."""
    payment = payments_svc.get_payment(
        db, tenant_id=tenant_id, payment_id=payment_id, location_ids=location_ids
    )
    value = moneylib.ensure_decimal(amount, field="amount")
    if value <= 0:
        raise ValidationError("refund amount must be positive")
    cleaned = (reason or "").strip()
    if len(cleaned) < 2 or len(cleaned) > 200:
        raise ValidationError("refund reason must be 2-200 characters")
    moneylib.validate_currency(payment.currency)
    invoice = None
    if invoice_id is not None:
        invoice = invoices_svc.get_invoice(
            db, tenant_id=tenant_id, invoice_id=invoice_id, location_ids=location_ids
        )
        if invoice.patient_id != payment.patient_id:
            raise ValidationError("payment and invoice belong to different patients")
    _lock_payment(db, payment_id=payment.id)
    key = (idempotency_key or "").strip() or None
    if key:
        existing = db.execute(
            select(Refund).where(
                Refund.tenant_id == tenant_id,
                Refund.idempotency_key == key,
            )
        ).scalar_one_or_none()
        if existing is not None:
            if not _refund_matches(
                existing, payment_id=payment.id, invoice_id=invoice_id, amount=value
            ):
                raise ConflictError("idempotency key was used for a different refund")
            return existing
    if invoice is not None:
        linked = _forward_rows_newest_first(db, payment_id=payment.id, invoice_id=invoice.id)
        if not linked:
            raise ValidationError("payment has no allocation to this invoice")
    refundable = payments_svc.refundable_for_payment(db, payment=payment)
    if value > refundable:
        raise ValidationError("refund exceeds the payment's refundable amount")
    # Reversal-first: free `value` from the affected allocations. Linked
    # refunds stay scoped to the linked invoice; payment-level refunds walk
    # every allocation newest-first.
    if invoice is not None:
        candidates = _forward_rows_newest_first(db, payment_id=payment.id, invoice_id=invoice.id)
        attributable = moneylib.quantize_half_up(
            sum(
                (moneylib.ensure_decimal(r.amount, field="amount") for r in candidates),
                payments_svc.unallocated_for_payment(db, payment=payment),
            )
        )
        if value > attributable:
            raise ConflictError("refund exceeds the amount attributable to the linked invoice")
    else:
        candidates = _forward_rows_newest_first(db, payment_id=payment.id)
    reversed_total = Decimal(0)
    last_invoice_id: uuid.UUID | None = None
    for row in candidates:
        if reversed_total >= value:
            break
        reversal = payments_svc.reverse_allocation(
            db,
            tenant_id=tenant_id,
            allocation_id=row.id,
            actor_id=actor_id,
            reason=f"refund of {value}",
            location_ids=location_ids,
        )
        reversed_total += moneylib.ensure_decimal(reversal.amount, field="amount")
        last_invoice_id = row.invoice_id
    excess = moneylib.quantize_half_up(reversed_total - value)
    if excess > 0 and last_invoice_id is not None:
        # Re-allocate the overshoot as a new explicit forward row so
        # exactly `value` leaves the allocation truth.
        re_row = PaymentAllocation(
            id=ids.uuid7(),
            tenant_id=tenant_id,
            patient_id=payment.patient_id,
            payment_id=payment.id,
            invoice_id=last_invoice_id,
            amount=excess,
            created_by=actor_id,
            created_at=_now(),
        )
        db.add(re_row)
        db.flush()
        re_invoice = invoices_svc.get_invoice(db, tenant_id=tenant_id, invoice_id=last_invoice_id)
        payments_svc.refresh_payment_state(db, payment=payment)
        invoices_svc.refresh_invoice_payment_state(db, invoice=re_invoice)
        db.flush()
    now = _now()
    refund = Refund(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        patient_id=payment.patient_id,
        payment_id=payment.id,
        invoice_id=invoice_id,
        status=M.REFUND_ISSUED,
        amount=value,
        currency=payment.currency,
        reason=cleaned,
        idempotency_key=key,
        created_by=actor_id,
        created_at=now,
        updated_at=now,
    )
    db.add(refund)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        retry = db.execute(
            select(Refund).where(
                Refund.tenant_id == tenant_id,
                Refund.idempotency_key == key,
            )
        ).scalar_one_or_none()
        if (
            retry is not None
            and key is not None
            and _refund_matches(retry, payment_id=payment_id, invoice_id=invoice_id, amount=value)
        ):
            return retry
        raise ConflictError("idempotency key was used for a different refund") from None
    payments_svc.refresh_payment_state(db, payment=payment)
    db.flush()
    return refund
