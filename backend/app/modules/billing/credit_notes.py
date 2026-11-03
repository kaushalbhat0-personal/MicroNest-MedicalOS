"""Credit note service (P4.6). Single authority for formal corrections
against exactly one issued invoice.

Lifecycle is `draft → issued`, with void-from-draft only. An issued note
is applied immediately through balance derivation
(`outstanding = total − allocated − credited`), so P4-01 §15's "void only
before application" means exactly this: issued notes are immutable and
never voided; further correction is a new note. Drafts carry no number;
the financial number is allocated at issue from the credit-note series
(tenant + location + FY + doc_type, Asia/Kolkata FY, advisory lock, gaps
accepted, duplicates impossible).

Caps: `amount ≤ outstanding at issue` — the outstanding that already
subtracts effective allocations AND previously issued credit notes, so
double-crediting is impossible and concurrent issuance serializes on the
invoice lock. Tax snapshot fields are explicit stored labels (P4-01 §6:
no GST engine); the caller supplies them, defaulting to a neutral
taxable-zero snapshot.
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
from app.modules.billing import numbering as numberinglib
from app.modules.billing.models import CreditNote
from app.platform import ids
from app.platform.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.platform.time import UTC


def _now() -> datetime:
    return datetime.now(UTC)


CREDIT_TRANSITIONS: dict[str, frozenset[str]] = {
    M.CREDIT_DRAFT: frozenset({M.CREDIT_ISSUED, M.CREDIT_VOIDED}),
    M.CREDIT_ISSUED: frozenset(),
    M.CREDIT_VOIDED: frozenset(),
}


def _lock_invoice(db: DBSession, *, invoice_id: uuid.UUID) -> None:
    """Serialize concurrent credit issuance against the same invoice — and
    against concurrent allocations, which take the same lock key."""
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key)::bigint)"),
        {"key": f"bill-alloc-inv:{invoice_id}"},
    )


def _lock_series(
    db: DBSession, *, tenant_id: uuid.UUID, location_id: uuid.UUID, financial_year: str
) -> None:
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key)::bigint)"),
        {"key": f"bill-cn-series:{tenant_id}:{location_id}:{financial_year}"},
    )


def get_credit_note(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    note_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> CreditNote:
    note = db.get(CreditNote, note_id)
    if note is None or note.tenant_id != tenant_id:
        raise NotFoundError("credit note not found")
    if location_ids and note.location_id not in location_ids:
        raise ForbiddenError("location is outside your scope")
    return note


def credit_notes_for_invoice(db: DBSession, *, invoice_id: uuid.UUID) -> list[CreditNote]:
    return list(
        db.execute(
            select(CreditNote)
            .where(CreditNote.invoice_id == invoice_id)
            .order_by(CreditNote.created_at, CreditNote.id)
        )
        .scalars()
        .all()
    )


def _validate_tax(
    *,
    tax_rate: object,
    tax_amount: object,
    hsn_sac: str | None,
    tax_treatment: str | None,
) -> tuple[Decimal, Decimal, str | None, str]:
    rate = moneylib.ensure_decimal(tax_rate, field="tax_rate")
    if rate < 0 or rate > 100:
        raise ValidationError("tax rate must be between 0 and 100")
    amount = moneylib.ensure_decimal(tax_amount, field="tax_amount")
    if amount < 0:
        raise ValidationError("tax amount must be non-negative")
    hsn = (hsn_sac or "").strip() or None
    if hsn is not None and len(hsn) > 16:
        raise ValidationError("hsn/sac must be at most 16 characters")
    treatment = (tax_treatment or "").strip().lower() or M.TAX_TAXABLE
    if treatment not in M.TAX_TREATMENTS:
        raise ValidationError("unknown tax treatment")
    return (
        moneylib.quantize_half_up(rate),
        moneylib.quantize_half_up(amount),
        hsn,
        treatment,
    )


def _note_matches(
    note: CreditNote,
    *,
    invoice_id: uuid.UUID,
    amount: Decimal,
    reason: str,
) -> bool:
    return (
        note.invoice_id == invoice_id
        and moneylib.ensure_decimal(note.amount, field="amount") == amount
        and note.reason == reason
    )


def _check_cap(db: DBSession, *, invoice_id: uuid.UUID, amount: Decimal) -> None:
    invoice = db.get(M.Invoice, invoice_id)
    if invoice is None:  # pragma: no cover — callers hold the invoice
        raise NotFoundError("invoice not found")
    outstanding = invoices_svc.outstanding_for_invoice(db, invoice=invoice)
    if amount > outstanding:
        raise ValidationError("credit note exceeds the invoice outstanding amount")


def create_credit_note(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    invoice_id: uuid.UUID,
    actor_id: uuid.UUID,
    amount: object,
    reason: str,
    tax_rate: object = 0,
    tax_amount: object = 0,
    hsn_sac: str | None = None,
    tax_treatment: str | None = None,
    idempotency_key: str | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> CreditNote:
    """Open a draft credit note against one invoice. Drafts are unnumbered
    proposals; the cap is enforced authoritatively at issue (and checked
    here for early feedback)."""
    invoice = invoices_svc.get_invoice(
        db, tenant_id=tenant_id, invoice_id=invoice_id, location_ids=location_ids
    )
    if invoice.status in (M.INVOICE_DRAFT, M.INVOICE_VOIDED):
        raise ConflictError(f"invoice {invoice.status} cannot be credited")
    value = moneylib.ensure_decimal(amount, field="amount")
    if value <= 0:
        raise ValidationError("credit note amount must be positive")
    cleaned = (reason or "").strip()
    if len(cleaned) < 2 or len(cleaned) > 200:
        raise ValidationError("credit note reason must be 2-200 characters")
    rate, tax, hsn, treatment = _validate_tax(
        tax_rate=tax_rate,
        tax_amount=tax_amount,
        hsn_sac=hsn_sac,
        tax_treatment=tax_treatment,
    )
    moneylib.validate_currency(invoice.currency)
    _lock_invoice(db, invoice_id=invoice.id)
    _check_cap(db, invoice_id=invoice.id, amount=value)
    key = (idempotency_key or "").strip() or None
    if key:
        existing = db.execute(
            select(CreditNote).where(
                CreditNote.tenant_id == tenant_id,
                CreditNote.idempotency_key == key,
            )
        ).scalar_one_or_none()
        if existing is not None:
            if not _note_matches(existing, invoice_id=invoice.id, amount=value, reason=cleaned):
                raise ConflictError("idempotency key was used for a different credit note")
            return existing
    now = _now()
    note = CreditNote(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        location_id=invoice.location_id,
        patient_id=invoice.patient_id,
        invoice_id=invoice.id,
        status=M.CREDIT_DRAFT,
        amount=value,
        currency=invoice.currency,
        tax_rate=rate,
        tax_amount=tax,
        hsn_sac=hsn,
        tax_treatment=treatment,
        reason=cleaned,
        idempotency_key=key,
        created_by=actor_id,
        created_at=now,
        updated_at=now,
    )
    db.add(note)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ConflictError("idempotency key was used for a different credit note") from None
    return note


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
            "SELECT COALESCE(MAX(doc_number), 0) FROM credit_notes "
            "WHERE tenant_id = :t AND location_id = :l AND financial_year = :fy"
        ),
        {"t": str(tenant_id), "l": str(location_id), "fy": financial_year},
    ).scalar_one()
    return int(current) + 1


def issue_credit_note(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    note_id: uuid.UUID,
    actor_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> CreditNote:
    """Issue a draft note: re-validate the cap against live balances,
    allocate the series number, freeze — atomically. Re-issuing is a
    no-op that never reallocates the number."""
    note = get_credit_note(db, tenant_id=tenant_id, note_id=note_id, location_ids=location_ids)
    if note.status == M.CREDIT_ISSUED:
        return note
    if note.status != M.CREDIT_DRAFT:
        raise ConflictError(f"cannot issue credit note from status {note.status}")
    _lock_invoice(db, invoice_id=note.invoice_id)
    value = moneylib.ensure_decimal(note.amount, field="amount")
    _check_cap(db, invoice_id=note.invoice_id, amount=value)
    fy = numberinglib.fy_for(_now())
    numberinglib.validate_fy(fy)
    note.financial_year = fy
    note.doc_number = _allocate_doc_number(
        db, tenant_id=note.tenant_id, location_id=note.location_id, financial_year=fy
    )
    note.status = M.CREDIT_ISSUED
    note.updated_at = _now()
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ConflictError("numbering conflict, retry the issue") from None
    return note


def void_credit_note(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    note_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
    reason: str | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> CreditNote:
    """Cancel an unnumbered draft. Issued notes are applied via derivation
    the moment they issue, so "void before application" ends at issue:
    issued notes are never voided (issue a new correcting note instead)."""
    note = get_credit_note(db, tenant_id=tenant_id, note_id=note_id, location_ids=location_ids)
    if note.status == M.CREDIT_VOIDED:
        return note
    if note.status != M.CREDIT_DRAFT:
        raise ConflictError("issued credit notes cannot be voided")
    cleaned = (reason or "").strip() or None
    if cleaned is not None and len(cleaned) > 200:
        raise ValidationError("void reason must be at most 200 characters")
    note.status = M.CREDIT_VOIDED
    note.updated_at = _now()
    db.flush()
    return note
