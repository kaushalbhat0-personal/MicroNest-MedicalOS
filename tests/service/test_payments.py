"""Payment + allocation domain (P4.5): recording, derived state, manual
allocation, reversal, patient credit, and balance-driven invoice states."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.modules.billing import invoices as inv
from app.modules.billing import models as M
from app.modules.billing import payments as pay
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


def _invoice(owner_db, b, rate: str = "100.00", **kw):  # type: ignore[no-untyped-def]
    args = {"actor_id": b["admin"].id, **_ids(b)}
    args.update(kw)
    invoice = inv.create_invoice(
        owner_db,
        **args,
        items=[{"description": "Care", "quantity": 1, "unit_rate": rate}],
    )
    return inv.issue_invoice(
        owner_db,
        tenant_id=b["tenant"].id,
        invoice_id=invoice.id,
        actor_id=b["admin"].id,
    )


def _payment(owner_db, b, amount: str = "100.00", **kw):  # type: ignore[no-untyped-def]
    args = {"actor_id": b["admin"].id, **_ids(b), "method": "cash", "amount": amount}
    args.update(kw)
    return pay.create_payment(owner_db, **args)


def test_record_payment_and_method_guards(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    payment = _payment(owner_db, b, amount="250.00", method="UPI")
    assert payment.status == M.PAYMENT_RECORDED
    assert payment.method == "upi"
    assert payment.currency == "INR"
    assert pay.unallocated_for_payment(db=owner_db, payment=payment) == Decimal(
        "250.00"
    )
    for bad in ("bitcoin", "", "card"):
        with pytest.raises(ValidationError):
            _payment(owner_db, b, method=bad)
    for bad_amount in ("0", "-5.00"):
        with pytest.raises(ValidationError):
            _payment(owner_db, b, amount=bad_amount)
    with pytest.raises(ValidationError):
        _payment(owner_db, b, currency="USD")
    assert pay.patient_credit(
        owner_db, tenant_id=b["tenant"].id, patient_id=b["patient"].id
    ) == Decimal("250.00")


def test_full_allocation_drives_paid(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    invoice = _invoice(owner_db, b, rate="100.00")
    payment = _payment(owner_db, b, amount="100.00")
    _, rows = pay.allocate_payment(
        owner_db,
        tenant_id=b["tenant"].id,
        payment_id=payment.id,
        actor_id=b["admin"].id,
        items=[{"invoice_id": invoice.id, "amount": "100.00"}],
    )
    assert len(rows) == 1 and rows[0].reversal_of_id is None
    assert payment.status == M.PAYMENT_ALLOCATED
    assert pay.unallocated_for_payment(db=owner_db, payment=payment) == Decimal("0.00")
    assert invoice.status == M.INVOICE_PAID
    assert inv.outstanding_for_invoice(db=owner_db, invoice=invoice) == Decimal("0.00")


def test_partial_allocation_and_credit_remainder(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    first = _invoice(owner_db, b, rate="60.00")
    second = _invoice(owner_db, b, rate="100.00")
    payment = _payment(owner_db, b, amount="200.00")
    pay.allocate_payment(
        owner_db,
        tenant_id=b["tenant"].id,
        payment_id=payment.id,
        actor_id=b["admin"].id,
        items=[{"invoice_id": first.id, "amount": "60.00"}],
    )
    assert payment.status == M.PAYMENT_PARTIALLY_ALLOCATED
    assert first.status == M.INVOICE_PAID
    assert pay.unallocated_for_payment(db=owner_db, payment=payment) == Decimal(
        "140.00"
    )
    # Overpayment is never forced onto the invoice: 140 remainder, 100 outstanding.
    with pytest.raises(ConflictError):
        pay.allocate_payment(
            owner_db,
            tenant_id=b["tenant"].id,
            payment_id=payment.id,
            actor_id=b["admin"].id,
            items=[{"invoice_id": second.id, "amount": "140.00"}],
        )
    pay.allocate_payment(
        owner_db,
        tenant_id=b["tenant"].id,
        payment_id=payment.id,
        actor_id=b["admin"].id,
        items=[{"invoice_id": second.id, "amount": "100.00"}],
    )
    assert second.status == M.INVOICE_PAID
    # The explicit 40.00 remainder survives as derived patient credit.
    assert pay.unallocated_for_payment(db=owner_db, payment=payment) == Decimal("40.00")
    assert pay.patient_credit(
        owner_db, tenant_id=b["tenant"].id, patient_id=b["patient"].id
    ) == Decimal("40.00")


def test_multi_payment_multi_invoice(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    invoice = _invoice(owner_db, b, rate="300.00")
    first_pay = _payment(owner_db, b, amount="100.00")
    second_pay = _payment(owner_db, b, amount="200.00")
    pay.allocate_payment(
        owner_db,
        tenant_id=b["tenant"].id,
        payment_id=first_pay.id,
        actor_id=b["admin"].id,
        items=[{"invoice_id": invoice.id, "amount": "100.00"}],
    )
    assert invoice.status == M.INVOICE_PARTIALLY_PAID
    assert inv.outstanding_for_invoice(db=owner_db, invoice=invoice) == Decimal(
        "200.00"
    )
    pay.allocate_payment(
        owner_db,
        tenant_id=b["tenant"].id,
        payment_id=second_pay.id,
        actor_id=b["admin"].id,
        items=[{"invoice_id": invoice.id, "amount": "200.00"}],
    )
    assert invoice.status == M.INVOICE_PAID
    # One allocate call may also split a payment across invoices explicitly.
    third = _invoice(owner_db, b, rate="50.00")
    fourth = _invoice(owner_db, b, rate="70.00")
    splitter = _payment(owner_db, b, amount="120.00")
    _, rows = pay.allocate_payment(
        owner_db,
        tenant_id=b["tenant"].id,
        payment_id=splitter.id,
        actor_id=b["admin"].id,
        items=[
            {"invoice_id": third.id, "amount": "50.00"},
            {"invoice_id": fourth.id, "amount": "70.00"},
        ],
    )
    assert len(rows) == 2
    assert third.status == M.INVOICE_PAID and fourth.status == M.INVOICE_PAID


def test_allocation_guards(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    from app.modules.patients import service as patients_service

    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    invoice = _invoice(owner_db, b, rate="100.00")
    payment = _payment(owner_db, b, amount="100.00")
    # Draft invoices are not open for allocation.
    draft = inv.create_invoice(
        owner_db,
        actor_id=b["admin"].id,
        **_ids(b),
        items=[{"description": "D", "quantity": 1, "unit_rate": "10.00"}],
    )
    with pytest.raises(ConflictError):
        pay.allocate_payment(
            owner_db,
            tenant_id=b["tenant"].id,
            payment_id=payment.id,
            actor_id=b["admin"].id,
            items=[{"invoice_id": draft.id, "amount": "10.00"}],
        )
    # Voided invoices are not open either.
    inv.void_invoice(owner_db, tenant_id=b["tenant"].id, invoice_id=draft.id)
    with pytest.raises(ConflictError):
        pay.allocate_payment(
            owner_db,
            tenant_id=b["tenant"].id,
            payment_id=payment.id,
            actor_id=b["admin"].id,
            items=[{"invoice_id": draft.id, "amount": "10.00"}],
        )
    # Cross-patient allocation is rejected (DB FKs back this up).
    other_patient = patients_service.register_patient(
        owner_db, tenant_id=b["tenant"].id, display_name="Other Pat"
    )
    owner_db.flush()
    alien_payment = _payment(owner_db, b, patient_id=other_patient.id, amount="100.00")
    with pytest.raises(ValidationError):
        pay.allocate_payment(
            owner_db,
            tenant_id=b["tenant"].id,
            payment_id=alien_payment.id,
            actor_id=b["admin"].id,
            items=[{"invoice_id": invoice.id, "amount": "10.00"}],
        )
    # Cross-tenant invoice reference is an oracle miss.
    other = provision_clinical(owner_db, make_owner_user, make_tenant, slug="pay-guard")
    foreign_invoice = inv.create_invoice(
        owner_db,
        actor_id=other["admin"].id,
        tenant_id=other["tenant"].id,
        location_id=other["location"].id,
        patient_id=other["patient"].id,
        items=[{"description": "F", "quantity": 1, "unit_rate": "10.00"}],
    )
    foreign_invoice = inv.issue_invoice(
        owner_db,
        tenant_id=other["tenant"].id,
        invoice_id=foreign_invoice.id,
        actor_id=other["admin"].id,
    )
    with pytest.raises(NotFoundError):
        pay.allocate_payment(
            owner_db,
            tenant_id=b["tenant"].id,
            payment_id=payment.id,
            actor_id=b["admin"].id,
            items=[{"invoice_id": foreign_invoice.id, "amount": "10.00"}],
        )
    # Zero / negative amounts and empty / duplicate requests rejected.
    for bad_items in ([], [{"invoice_id": invoice.id, "amount": "0"}]):
        with pytest.raises((ValidationError, ConflictError)):
            pay.allocate_payment(
                owner_db,
                tenant_id=b["tenant"].id,
                payment_id=payment.id,
                actor_id=b["admin"].id,
                items=bad_items,
            )
    with pytest.raises(ValidationError):
        pay.allocate_payment(
            owner_db,
            tenant_id=b["tenant"].id,
            payment_id=payment.id,
            actor_id=b["admin"].id,
            items=[
                {"invoice_id": invoice.id, "amount": "10.00"},
                {"invoice_id": invoice.id, "amount": "10.00"},
            ],
        )
    # Location scope is fail-closed on both legs.
    with pytest.raises(ForbiddenError):
        pay.allocate_payment(
            owner_db,
            tenant_id=b["tenant"].id,
            payment_id=payment.id,
            actor_id=b["admin"].id,
            items=[{"invoice_id": invoice.id, "amount": "10.00"}],
            location_ids=frozenset({uuid.uuid4()}),
        )


def test_reversal_restores_balances(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    invoice = _invoice(owner_db, b, rate="100.00")
    payment = _payment(owner_db, b, amount="100.00")
    _, rows = pay.allocate_payment(
        owner_db,
        tenant_id=b["tenant"].id,
        payment_id=payment.id,
        actor_id=b["admin"].id,
        items=[{"invoice_id": invoice.id, "amount": "100.00"}],
    )
    assert invoice.status == M.INVOICE_PAID
    reversal = pay.reverse_allocation(
        owner_db,
        tenant_id=b["tenant"].id,
        allocation_id=rows[0].id,
        actor_id=b["admin"].id,
        reason="wrong invoice",
    )
    assert reversal.reversal_of_id == rows[0].id
    assert invoice.status == M.INVOICE_ISSUED
    assert payment.status == M.PAYMENT_RECORDED
    assert pay.unallocated_for_payment(db=owner_db, payment=payment) == Decimal(
        "100.00"
    )
    # One reversal per allocation; reversals cannot be reversed.
    with pytest.raises(ConflictError):
        pay.reverse_allocation(
            owner_db,
            tenant_id=b["tenant"].id,
            allocation_id=rows[0].id,
            actor_id=b["admin"].id,
            reason="again",
        )
    with pytest.raises(ConflictError):
        pay.reverse_allocation(
            owner_db,
            tenant_id=b["tenant"].id,
            allocation_id=reversal.id,
            actor_id=b["admin"].id,
            reason="reversal of reversal",
        )
    with pytest.raises(ValidationError):
        pay.reverse_allocation(
            owner_db,
            tenant_id=b["tenant"].id,
            allocation_id=rows[0].id,
            actor_id=b["admin"].id,
            reason="x",
        )
    # Fully reversed invoice is voidable again.
    voided = inv.void_invoice(
        owner_db,
        tenant_id=b["tenant"].id,
        invoice_id=invoice.id,
        actor_id=b["admin"].id,
        reason="cancel after reversal",
    )
    assert voided.status == M.INVOICE_VOIDED


def test_payment_idempotency(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    from app.modules.patients import service as patients_service

    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    first = _payment(owner_db, b, amount="100.00", idempotency_key="pay-key-1")
    replay = _payment(owner_db, b, amount="100.00", idempotency_key="pay-key-1")
    assert replay.id == first.id
    with pytest.raises(ConflictError):
        _payment(owner_db, b, amount="150.00", idempotency_key="pay-key-1")
    other_patient = patients_service.register_patient(
        owner_db, tenant_id=b["tenant"].id, display_name="Divergent Pat"
    )
    owner_db.flush()
    with pytest.raises(ConflictError):
        _payment(owner_db, b, patient_id=other_patient.id, idempotency_key="pay-key-1")


def test_allocate_idempotency(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    first_invoice = _invoice(owner_db, b, rate="60.00")
    second_invoice = _invoice(owner_db, b, rate="40.00")
    payment = _payment(owner_db, b, amount="100.00")
    _, first_rows = pay.allocate_payment(
        owner_db,
        tenant_id=b["tenant"].id,
        payment_id=payment.id,
        actor_id=b["admin"].id,
        items=[{"invoice_id": first_invoice.id, "amount": "60.00"}],
        idempotency_key="alloc-key-1",
    )
    _, replay_rows = pay.allocate_payment(
        owner_db,
        tenant_id=b["tenant"].id,
        payment_id=payment.id,
        actor_id=b["admin"].id,
        items=[{"invoice_id": first_invoice.id, "amount": "60.00"}],
        idempotency_key="alloc-key-1",
    )
    assert [row.id for row in replay_rows] == [row.id for row in first_rows]
    # Same key, divergent invoice intent → conflict.
    with pytest.raises(ConflictError):
        pay.allocate_payment(
            owner_db,
            tenant_id=b["tenant"].id,
            payment_id=payment.id,
            actor_id=b["admin"].id,
            items=[{"invoice_id": second_invoice.id, "amount": "60.00"}],
            idempotency_key="alloc-key-1",
        )
