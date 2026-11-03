"""Receipt service (P4.7). Single authority for payment evidence.

Receipt = evidence of payment; payment remains the financial source of
truth (P4-01 section 16). One receipt per payment capture (1:1 in P4;
split receipts deferred). Immutable, numbered per section 10 series at
creation. Stores ``payment_id`` plus the payment amount/currency snapshot
as it existed at creation — later allocations, reversals, or refunds
never rewrite the receipt.

Receipt creation never mutates payment state, never allocates, never
refunds, and never creates patient credit.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.modules.billing import money as moneylib
from app.modules.billing import numbering as numberinglib
from app.modules.billing import payments as payments_svc
from app.modules.billing.models import Receipt
from app.platform import ids
from app.platform.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.platform.time import UTC


def _now() -> datetime:
    return datetime.now(UTC)


def _lock_payment(db: DBSession, *, payment_id: uuid.UUID) -> None:
    """Serialize concurrent receipt creation on the same payment."""
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key)::bigint)"),
        {"key": f"bill-pay:{payment_id}"},
    )


def _lock_series(
    db: DBSession, *, tenant_id: uuid.UUID, location_id: uuid.UUID, financial_year: str
) -> None:
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key)::bigint)"),
        {"key": f"bill-receipt-series:{tenant_id}:{location_id}:{financial_year}"},
    )


def get_receipt(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    receipt_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Receipt:
    receipt = db.get(Receipt, receipt_id)
    if receipt is None or receipt.tenant_id != tenant_id:
        raise NotFoundError("receipt not found")
    if location_ids and receipt.location_id not in location_ids:
        raise ForbiddenError("location is outside your scope")
    return receipt


def receipt_for_payment(
    db: DBSession,
    *,
    payment_id: uuid.UUID,
) -> Receipt | None:
    """Existing receipt for a payment, if any. Enforces the 0-or-1 leg."""
    return db.execute(select(Receipt).where(Receipt.payment_id == payment_id)).scalar_one_or_none()


def _allocate_doc_number(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID,
    financial_year: str,
) -> int:
    _lock_series(db, tenant_id=tenant_id, location_id=location_id, financial_year=financial_year)
    current = db.execute(
        text(
            "SELECT COALESCE(MAX(doc_number), 0) FROM receipts "
            "WHERE tenant_id = :t AND location_id = :l AND financial_year = :fy"
        ),
        {"t": str(tenant_id), "l": str(location_id), "fy": financial_year},
    ).scalar_one()
    return int(current) + 1


def create_receipt(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    payment_id: uuid.UUID,
    actor_id: uuid.UUID,
    idempotency_key: str | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Receipt:
    """Issue the single immutable receipt evidencing a recorded payment.

    Snapshot semantics: ``amount``/``currency`` are copied from the payment
    as it exists at creation and never updated afterwards — later
    allocations, reversals, or refunds change derived balances only.
    """
    payment = payments_svc.get_payment(
        db, tenant_id=tenant_id, payment_id=payment_id, location_ids=location_ids
    )
    moneylib.validate_currency(payment.currency)
    amount = moneylib.quantize_half_up(moneylib.ensure_decimal(payment.amount, field="amount"))
    if amount <= 0:
        raise ValidationError("payment amount must be positive")
    _lock_payment(db, payment_id=payment.id)
    key = (idempotency_key or "").strip() or None
    if key:
        existing = db.execute(
            select(Receipt).where(
                Receipt.tenant_id == tenant_id,
                Receipt.idempotency_key == key,
            )
        ).scalar_one_or_none()
        if existing is not None:
            if existing.payment_id != payment.id:
                raise ConflictError("idempotency key was used for a different receipt")
            return existing
    already = receipt_for_payment(db, payment_id=payment.id)
    if already is not None:
        raise ConflictError("receipt already exists for this payment")
    fy = numberinglib.fy_for(_now())
    numberinglib.validate_fy(fy)
    doc_number = _allocate_doc_number(
        db, tenant_id=payment.tenant_id, location_id=payment.location_id, financial_year=fy
    )
    receipt = Receipt(
        id=ids.uuid7(),
        tenant_id=payment.tenant_id,
        location_id=payment.location_id,
        payment_id=payment.id,
        patient_id=payment.patient_id,
        amount=amount,
        currency=payment.currency,
        financial_year=fy,
        doc_number=doc_number,
        idempotency_key=key,
        created_by=actor_id,
        created_at=_now(),
    )
    db.add(receipt)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        if key:
            retry = db.execute(
                select(Receipt).where(
                    Receipt.tenant_id == tenant_id,
                    Receipt.idempotency_key == key,
                )
            ).scalar_one_or_none()
            if retry is not None:
                if retry.payment_id != payment.id:
                    raise ConflictError(
                        "idempotency key was used for a different receipt"
                    ) from None
                return retry
        conflict = receipt_for_payment(db, payment_id=payment.id)
        if conflict is not None:
            raise ConflictError("receipt already exists for this payment") from None
        raise ConflictError("numbering conflict, retry the receipt") from None
    return receipt
