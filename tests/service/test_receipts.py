"""Receipt foundation domain (P4.7): evidence-only, 1:1, numbering, idempotency."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.modules.billing import invoices as inv
from app.modules.billing import models as M
from app.modules.billing import numbering as numberinglib
from app.modules.billing import payments as pay
from app.modules.billing import receipts as rcpt
from app.modules.billing import refunds as ref
from app.platform.errors import ConflictError, ForbiddenError, NotFoundError
from tests.helpers import provision_clinical


def _ids(b):  # type: ignore[no-untyped-def]
    return {
        "tenant_id": b["tenant"].id,
        "location_id": b["location"].id,
        "patient_id": b["patient"].id,
    }


def _payment(owner_db, b, amount: str = "100.00"):  # type: ignore[no-untyped-def]
    return pay.create_payment(
        owner_db, actor_id=b["admin"].id, **_ids(b), method="cash", amount=amount
    )


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


def test_create_receipt_snapshots_payment(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    payment = _payment(owner_db, b, amount="250.00")
    receipt = rcpt.create_receipt(
        owner_db,
        tenant_id=b["tenant"].id,
        payment_id=payment.id,
        actor_id=b["admin"].id,
    )
    assert receipt.payment_id == payment.id
    assert receipt.tenant_id == payment.tenant_id
    assert receipt.location_id == payment.location_id
    assert receipt.patient_id == payment.patient_id
    assert receipt.amount == Decimal("250.00")
    assert receipt.currency == "INR"
    assert receipt.doc_number == 1
    assert receipt.financial_year == numberinglib.fy_for(receipt.created_at)
    assert receipt.idempotency_key is None
    # Payment row untouched: receipt creation mutates nothing financial.
    assert payment.amount == Decimal("250.00")
    assert payment.status == M.PAYMENT_RECORDED


def test_receipt_snapshot_frozen_across_allocation_and_refund(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    invoice = _invoice(owner_db, b, rate="100.00")
    payment = _payment(owner_db, b, amount="100.00")
    receipt = rcpt.create_receipt(
        owner_db,
        tenant_id=b["tenant"].id,
        payment_id=payment.id,
        actor_id=b["admin"].id,
    )
    snap_amount = receipt.amount
    pay.allocate_payment(
        owner_db,
        tenant_id=b["tenant"].id,
        payment_id=payment.id,
        actor_id=b["admin"].id,
        items=[{"invoice_id": invoice.id, "amount": "100.00"}],
    )
    ref.create_refund(
        owner_db,
        tenant_id=b["tenant"].id,
        payment_id=payment.id,
        actor_id=b["admin"].id,
        amount="100.00",
        reason="service not rendered",
    )
    fresh = rcpt.get_receipt(owner_db, tenant_id=b["tenant"].id, receipt_id=receipt.id)
    assert fresh.amount == snap_amount == Decimal("100.00")
    # Receipt carries no balance legs: only amount/currency snapshot.
    assert not hasattr(fresh, "allocated_amount")
    assert not hasattr(fresh, "outstanding_amount")


def test_receipt_numbering_sequential_per_series(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    first = rcpt.create_receipt(
        owner_db,
        tenant_id=b["tenant"].id,
        payment_id=_payment(owner_db, b, amount="10.00").id,
        actor_id=b["admin"].id,
    )
    second = rcpt.create_receipt(
        owner_db,
        tenant_id=b["tenant"].id,
        payment_id=_payment(owner_db, b, amount="20.00").id,
        actor_id=b["admin"].id,
    )
    assert second.doc_number == first.doc_number + 1
    assert second.financial_year == first.financial_year


def test_one_to_one_payment_invariant(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    payment = _payment(owner_db, b, amount="100.00")
    rcpt.create_receipt(
        owner_db,
        tenant_id=b["tenant"].id,
        payment_id=payment.id,
        actor_id=b["admin"].id,
    )
    with pytest.raises(ConflictError):
        rcpt.create_receipt(
            owner_db,
            tenant_id=b["tenant"].id,
            payment_id=payment.id,
            actor_id=b["admin"].id,
        )
    with pytest.raises(ConflictError):
        rcpt.create_receipt(
            owner_db,
            tenant_id=b["tenant"].id,
            payment_id=payment.id,
            actor_id=b["admin"].id,
            idempotency_key="different-key",
        )
    assert rcpt.receipt_for_payment(db=owner_db, payment_id=payment.id) is not None


def test_receipt_idempotency(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    payment = _payment(owner_db, b, amount="100.00")
    other = _payment(owner_db, b, amount="100.00")
    first = rcpt.create_receipt(
        owner_db,
        tenant_id=b["tenant"].id,
        payment_id=payment.id,
        actor_id=b["admin"].id,
        idempotency_key="rcpt-key-1",
    )
    replay = rcpt.create_receipt(
        owner_db,
        tenant_id=b["tenant"].id,
        payment_id=payment.id,
        actor_id=b["admin"].id,
        idempotency_key="rcpt-key-1",
    )
    assert replay.id == first.id
    assert replay.doc_number == first.doc_number
    with pytest.raises(ConflictError):
        rcpt.create_receipt(
            owner_db,
            tenant_id=b["tenant"].id,
            payment_id=other.id,
            actor_id=b["admin"].id,
            idempotency_key="rcpt-key-1",
        )


def test_payment_eligibility_guards(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    with pytest.raises(NotFoundError):
        rcpt.create_receipt(
            owner_db,
            tenant_id=b["tenant"].id,
            payment_id=uuid.uuid4(),
            actor_id=b["admin"].id,
        )
    other = provision_clinical(owner_db, make_owner_user, make_tenant, slug="rcpt-elig")
    foreign = _payment(owner_db, other, amount="50.00")
    with pytest.raises(NotFoundError):
        rcpt.create_receipt(
            owner_db,
            tenant_id=b["tenant"].id,
            payment_id=foreign.id,
            actor_id=b["admin"].id,
        )
    payment = _payment(owner_db, b, amount="100.00")
    with pytest.raises(ForbiddenError):
        rcpt.create_receipt(
            owner_db,
            tenant_id=b["tenant"].id,
            payment_id=payment.id,
            actor_id=b["admin"].id,
            location_ids=frozenset({uuid.uuid4()}),
        )
    with pytest.raises(ForbiddenError):
        rcpt.get_receipt(
            owner_db,
            tenant_id=b["tenant"].id,
            receipt_id=rcpt.create_receipt(
                owner_db,
                tenant_id=b["tenant"].id,
                payment_id=payment.id,
                actor_id=b["admin"].id,
            ).id,
            location_ids=frozenset({uuid.uuid4()}),
        )
    with pytest.raises(NotFoundError):
        rcpt.get_receipt(owner_db, tenant_id=b["tenant"].id, receipt_id=uuid.uuid4())


def test_receipt_module_has_no_mutation_surface() -> None:  # type: ignore[no-untyped-def]
    import pathlib

    src = pathlib.Path("backend/app/modules/billing/receipts.py").read_text()
    for forbidden in (
        "def update_",
        "def void_",
        "def delete_",
        "def reverse_",
        "def refund_",
    ):
        assert forbidden not in src
