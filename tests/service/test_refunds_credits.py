"""Refund + credit note domain (P4.6): caps, reversal-first refunds,
invoice correction semantics, independence matrix, patient credit."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.modules.billing import credit_notes as cn
from app.modules.billing import invoices as inv
from app.modules.billing import models as M
from app.modules.billing import payments as pay
from app.modules.billing import refunds as ref
from app.platform.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from tests.helpers import provision_clinical


def _ids(b):  # type: ignore[no-untyped-def]
    return {
        "tenant_id": b["tenant"].id,
        "location_id": b["location"].id,
        "patient_id": b["patient"].id,
    }


def _invoice(owner_db, b, rate: str = "100.00"):  # type: ignore[no-untyped-def]
    invoice = inv.create_invoice(
        owner_db,
        actor_id=b["admin"].id,
        **_ids(b),
        items=[{"description": "Care", "quantity": 1, "unit_rate": rate}],
    )
    return inv.issue_invoice(
        owner_db,
        tenant_id=b["tenant"].id,
        invoice_id=invoice.id,
        actor_id=b["admin"].id,
    )


def _payment(owner_db, b, amount: str = "100.00"):  # type: ignore[no-untyped-def]
    return pay.create_payment(
        owner_db, actor_id=b["admin"].id, **_ids(b), method="cash", amount=amount
    )


def _allocate(owner_db, b, payment, invoice, amount: str):  # type: ignore[no-untyped-def]
    _, rows = pay.allocate_payment(
        owner_db,
        tenant_id=b["tenant"].id,
        payment_id=payment.id,
        actor_id=b["admin"].id,
        items=[{"invoice_id": invoice.id, "amount": amount}],
    )
    return rows


def _issue_note(owner_db, b, invoice, amount: str, reason: str = "billing error"):  # type: ignore[no-untyped-def]
    note = cn.create_credit_note(
        owner_db,
        tenant_id=b["tenant"].id,
        invoice_id=invoice.id,
        actor_id=b["admin"].id,
        amount=amount,
        reason=reason,
    )
    assert note.status == M.CREDIT_DRAFT and note.doc_number is None
    return cn.issue_credit_note(
        owner_db, tenant_id=b["tenant"].id, note_id=note.id, actor_id=b["admin"].id
    )


def test_payment_level_refund_of_unallocated(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    payment = _payment(owner_db, b, amount="250.00")
    refund = ref.create_refund(
        owner_db,
        tenant_id=b["tenant"].id,
        payment_id=payment.id,
        actor_id=b["admin"].id,
        amount="100.00",
        reason="duplicate charge",
    )
    assert refund.status == M.REFUND_ISSUED
    assert refund.invoice_id is None
    assert refund.reason == "duplicate charge"
    assert money(payment, owner_db) == ("250.00", "0.00", "100.00", "150.00")
    assert payment.status == M.PAYMENT_PARTIALLY_REFUNDED
    # Original payment row immutable: captured amount untouched.
    assert payment.amount == Decimal("250.00")
    assert pay.patient_credit(
        owner_db, tenant_id=b["tenant"].id, patient_id=b["patient"].id
    ) == Decimal("150.00")


def money(payment, owner_db):  # type: ignore[no-untyped-def]
    return (
        str(payment.amount),
        str(pay.allocated_for_payment(db=owner_db, payment=payment)),
        str(pay.effective_refunded(db=owner_db, payment_id=payment.id)),
        str(pay.unallocated_for_payment(db=owner_db, payment=payment)),
    )


def test_full_refund_reverses_allocations(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    """P4-01 §6 scenario: 1000 paid, 1000 allocated, 1000 refunded must not
    leave the invoice PAID."""
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    invoice = _invoice(owner_db, b, rate="1000.00")
    payment = _payment(owner_db, b, amount="1000.00")
    _allocate(owner_db, b, payment, invoice, "1000.00")
    assert invoice.status == M.INVOICE_PAID
    refund = ref.create_refund(
        owner_db,
        tenant_id=b["tenant"].id,
        payment_id=payment.id,
        actor_id=b["admin"].id,
        amount="1000.00",
        reason="service not rendered",
    )
    assert refund.status == M.REFUND_ISSUED
    # Allocation truth moved first: the invoice is back to issued...
    assert invoice.status == M.INVOICE_ISSUED
    assert inv.outstanding_for_invoice(db=owner_db, invoice=invoice) == Decimal(
        "1000.00"
    )
    # ...while the money-return tracks on the payment.
    assert money(payment, owner_db) == ("1000.00", "0.00", "1000.00", "0.00")
    assert payment.status == M.PAYMENT_REFUNDED
    assert pay.refundable_for_payment(db=owner_db, payment=payment) == Decimal("0.00")


def test_partial_refund_with_excess_reallocation(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    first = _invoice(owner_db, b, rate="100.00")
    second = _invoice(owner_db, b, rate="100.00")
    payment = _payment(owner_db, b, amount="300.00")
    _allocate(owner_db, b, payment, first, "100.00")
    _allocate(owner_db, b, payment, second, "100.00")
    assert pay.unallocated_for_payment(db=owner_db, payment=payment) == Decimal(
        "100.00"
    )
    # Refund 150: reverses newest-first (second 100, then first 100 = 200
    # freed) and re-allocates the 50 overshoot to the last-touched invoice.
    refund = ref.create_refund(
        owner_db,
        tenant_id=b["tenant"].id,
        payment_id=payment.id,
        actor_id=b["admin"].id,
        amount="150.00",
        reason="partial return",
    )
    assert refund.amount == Decimal("150.00")
    # Exactly 150 left the allocation truth: 200 reversed, 50 re-allocated.
    assert money(payment, owner_db) == ("300.00", "50.00", "150.00", "100.00")
    assert payment.status == M.PAYMENT_PARTIALLY_REFUNDED
    # The re-allocated 50 sits on one invoice. Timestamp ties fall back to
    # id order, so assert the multiset rather than which leg holds it.
    assert sorted(
        [
            inv.outstanding_for_invoice(db=owner_db, invoice=first),
            inv.outstanding_for_invoice(db=owner_db, invoice=second),
        ]
    ) == [Decimal("50.00"), Decimal("100.00")]


def test_refund_caps_and_linkage(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    from app.modules.patients import service as patients_service

    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    invoice = _invoice(owner_db, b, rate="100.00")
    payment = _payment(owner_db, b, amount="100.00")
    # Policy-literal: over-refund is a ValidationError, never a clamp.
    with pytest.raises(ValidationError):
        ref.create_refund(
            owner_db,
            tenant_id=b["tenant"].id,
            payment_id=payment.id,
            actor_id=b["admin"].id,
            amount="100.01",
            reason="too much",
        )
    with pytest.raises(ValidationError):
        ref.create_refund(
            owner_db,
            tenant_id=b["tenant"].id,
            payment_id=payment.id,
            actor_id=b["admin"].id,
            amount="0",
            reason="zero",
        )
    with pytest.raises(ValidationError):
        ref.create_refund(
            owner_db,
            tenant_id=b["tenant"].id,
            payment_id=payment.id,
            actor_id=b["admin"].id,
            amount="10.00",
            reason="x",
        )
    # Linked refund requires a real payment→invoice allocation history.
    with pytest.raises(ValidationError):
        ref.create_refund(
            owner_db,
            tenant_id=b["tenant"].id,
            payment_id=payment.id,
            actor_id=b["admin"].id,
            amount="10.00",
            reason="linked",
            invoice_id=invoice.id,
        )
    _allocate(owner_db, b, payment, invoice, "100.00")
    linked = ref.create_refund(
        owner_db,
        tenant_id=b["tenant"].id,
        payment_id=payment.id,
        actor_id=b["admin"].id,
        amount="40.00",
        reason="linked return",
        invoice_id=invoice.id,
    )
    assert linked.invoice_id == invoice.id
    assert inv.outstanding_for_invoice(db=owner_db, invoice=invoice) == Decimal("40.00")
    # Cross-patient linkage rejected.
    stranger = patients_service.register_patient(
        owner_db, tenant_id=b["tenant"].id, display_name="Stranger"
    )
    owner_db.flush()
    alien_invoice = inv.create_invoice(
        owner_db,
        actor_id=b["admin"].id,
        tenant_id=b["tenant"].id,
        location_id=b["location"].id,
        patient_id=stranger.id,
        items=[{"description": "X", "quantity": 1, "unit_rate": "10.00"}],
    )
    alien_invoice = inv.issue_invoice(
        owner_db,
        tenant_id=b["tenant"].id,
        invoice_id=alien_invoice.id,
        actor_id=b["admin"].id,
    )
    with pytest.raises(ValidationError):
        ref.create_refund(
            owner_db,
            tenant_id=b["tenant"].id,
            payment_id=payment.id,
            actor_id=b["admin"].id,
            amount="5.00",
            reason="alien",
            invoice_id=alien_invoice.id,
        )
    # Second refund beyond the remainder is rejected.
    with pytest.raises(ValidationError):
        ref.create_refund(
            owner_db,
            tenant_id=b["tenant"].id,
            payment_id=payment.id,
            actor_id=b["admin"].id,
            amount="70.00",
            reason="over remainder",
        )
    # Reason is mandatory; unknown refund is a 404 oracle miss.
    with pytest.raises(NotFoundError):
        ref.get_refund(owner_db, tenant_id=b["tenant"].id, refund_id=uuid.uuid4())


def test_refund_idempotency(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    payment = _payment(owner_db, b, amount="100.00")
    first = ref.create_refund(
        owner_db,
        tenant_id=b["tenant"].id,
        payment_id=payment.id,
        actor_id=b["admin"].id,
        amount="30.00",
        reason="idem",
        idempotency_key="ref-key-1",
    )
    replay = ref.create_refund(
        owner_db,
        tenant_id=b["tenant"].id,
        payment_id=payment.id,
        actor_id=b["admin"].id,
        amount="30.00",
        reason="idem",
        idempotency_key="ref-key-1",
    )
    assert replay.id == first.id
    assert pay.effective_refunded(db=owner_db, payment_id=payment.id) == Decimal(
        "30.00"
    )
    with pytest.raises(ConflictError):
        ref.create_refund(
            owner_db,
            tenant_id=b["tenant"].id,
            payment_id=payment.id,
            actor_id=b["admin"].id,
            amount="40.00",
            reason="idem",
            idempotency_key="ref-key-1",
        )


def test_credit_note_lifecycle_and_numbering(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from app.modules.billing import numbering as numberinglib

    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    invoice = _invoice(owner_db, b, rate="500.00")
    note = _issue_note(owner_db, b, invoice, "120.00")
    assert note.status == M.CREDIT_ISSUED
    assert note.invoice_id == invoice.id
    assert note.location_id == invoice.location_id
    assert note.patient_id == invoice.patient_id
    assert note.doc_number == 1
    assert note.financial_year == numberinglib.fy_for(note.created_at)
    # Same-state re-issue is a no-op: no renumbering.
    again = cn.issue_credit_note(
        owner_db, tenant_id=b["tenant"].id, note_id=note.id, actor_id=b["admin"].id
    )
    assert again.id == note.id and again.doc_number == 1
    second = _issue_note(owner_db, b, invoice, "30.00", reason="second adjustment")
    assert second.doc_number == 2
    # Draft cancellation works; issued notes are never voided.
    draft = cn.create_credit_note(
        owner_db,
        tenant_id=b["tenant"].id,
        invoice_id=invoice.id,
        actor_id=b["admin"].id,
        amount="10.00",
        reason="drafted",
    )
    voided = cn.void_credit_note(
        owner_db, tenant_id=b["tenant"].id, note_id=draft.id, actor_id=b["admin"].id
    )
    assert voided.status == M.CREDIT_VOIDED
    with pytest.raises(ConflictError):
        cn.void_credit_note(
            owner_db, tenant_id=b["tenant"].id, note_id=note.id, actor_id=b["admin"].id
        )
    with pytest.raises(ConflictError):
        cn.issue_credit_note(
            owner_db,
            tenant_id=b["tenant"].id,
            note_id=voided.id,
            actor_id=b["admin"].id,
        )


def test_credit_note_affects_outstanding_not_status(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    invoice = _invoice(owner_db, b, rate="500.00")
    payment = _payment(owner_db, b, amount="500.00")
    _allocate(owner_db, b, payment, invoice, "200.00")
    assert invoice.status == M.INVOICE_PARTIALLY_PAID
    _issue_note(owner_db, b, invoice, "300.00")
    # Collectible outstanding hits zero; status follows allocation truth only.
    assert inv.outstanding_for_invoice(db=owner_db, invoice=invoice) == Decimal("0.00")
    assert invoice.status == M.INVOICE_PARTIALLY_PAID
    # Over-credit beyond outstanding is rejected (no excess notes).
    with pytest.raises(ValidationError):
        _issue_note(owner_db, b, invoice, "0.01")
    # Credit never touches the payment or patient credit.
    assert money(payment, owner_db) == ("500.00", "200.00", "0.00", "300.00")
    assert pay.patient_credit(
        owner_db, tenant_id=b["tenant"].id, patient_id=b["patient"].id
    ) == Decimal("300.00")
    # Invoice financial truth untouched.
    assert invoice.grand_total == Decimal("500.00")
    assert len(inv.invoice_lines(db=owner_db, invoice_id=invoice.id)) == 1


def test_credit_note_caps_and_guards(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    invoice = _invoice(owner_db, b, rate="100.00")
    _issue_note(owner_db, b, invoice, "60.00")
    # Second note capped at the remaining outstanding (double-credit blocked).
    with pytest.raises(ValidationError):
        _issue_note(owner_db, b, invoice, "60.00", reason="double credit")
    ok = _issue_note(owner_db, b, invoice, "40.00", reason="remainder")
    assert ok.status == M.CREDIT_ISSUED
    with pytest.raises(ValidationError):
        _issue_note(owner_db, b, invoice, "0.01", reason="over credited")
    with pytest.raises(ValidationError):
        cn.create_credit_note(
            owner_db,
            tenant_id=b["tenant"].id,
            invoice_id=invoice.id,
            actor_id=b["admin"].id,
            amount="5.00",
            reason="x",
        )
    # Draft and voided invoices cannot be credited.
    draft = inv.create_invoice(
        owner_db,
        actor_id=b["admin"].id,
        **_ids(b),
        items=[{"description": "D", "quantity": 1, "unit_rate": "10.00"}],
    )
    with pytest.raises(ConflictError):
        cn.create_credit_note(
            owner_db,
            tenant_id=b["tenant"].id,
            invoice_id=draft.id,
            actor_id=b["admin"].id,
            amount="5.00",
            reason="draft invoice",
        )
    with pytest.raises(NotFoundError):
        cn.get_credit_note(owner_db, tenant_id=b["tenant"].id, note_id=uuid.uuid4())
    with pytest.raises(ForbiddenError):
        cn.get_credit_note(
            owner_db,
            tenant_id=b["tenant"].id,
            note_id=ok.id,
            location_ids=frozenset({uuid.uuid4()}),
        )


def test_credit_note_idempotency(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    other = _invoice(owner_db, b, rate="100.00")
    invoice = _invoice(owner_db, b, rate="100.00")
    first = cn.create_credit_note(
        owner_db,
        tenant_id=b["tenant"].id,
        invoice_id=invoice.id,
        actor_id=b["admin"].id,
        amount="25.00",
        reason="idem note",
        idempotency_key="cn-key-1",
    )
    replay = cn.create_credit_note(
        owner_db,
        tenant_id=b["tenant"].id,
        invoice_id=invoice.id,
        actor_id=b["admin"].id,
        amount="25.00",
        reason="idem note",
        idempotency_key="cn-key-1",
    )
    assert replay.id == first.id
    with pytest.raises(ConflictError):
        cn.create_credit_note(
            owner_db,
            tenant_id=b["tenant"].id,
            invoice_id=other.id,
            actor_id=b["admin"].id,
            amount="25.00",
            reason="idem note",
            idempotency_key="cn-key-1",
        )


def test_refund_credit_matrix(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    """The four concepts stay separate: allocation, reversal, refund,
    credit note, and patient payment credit."""
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    invoice = _invoice(owner_db, b, rate="400.00")
    payment = _payment(owner_db, b, amount="500.00")
    rows = _allocate(owner_db, b, payment, invoice, "400.00")
    assert invoice.status == M.INVOICE_PAID
    # Reversal: touches payment + invoice, returns no money.
    pay.reverse_allocation(
        owner_db,
        tenant_id=b["tenant"].id,
        allocation_id=rows[0].id,
        actor_id=b["admin"].id,
        reason="matrix",
    )
    assert invoice.status == M.INVOICE_ISSUED
    assert pay.effective_refunded(db=owner_db, payment_id=payment.id) == Decimal("0.00")
    # Credit note: touches invoice outstanding only — payment untouched.
    _issue_note(owner_db, b, invoice, "100.00")
    assert invoice.status == M.INVOICE_ISSUED
    assert money(payment, owner_db) == ("500.00", "0.00", "0.00", "500.00")
    # Refund: returns money — refundable drops, patient credit drops.
    ref.create_refund(
        owner_db,
        tenant_id=b["tenant"].id,
        payment_id=payment.id,
        actor_id=b["admin"].id,
        amount="200.00",
        reason="matrix refund",
    )
    assert money(payment, owner_db) == ("500.00", "0.00", "200.00", "300.00")
    assert pay.patient_credit(
        owner_db, tenant_id=b["tenant"].id, patient_id=b["patient"].id
    ) == Decimal("300.00")
