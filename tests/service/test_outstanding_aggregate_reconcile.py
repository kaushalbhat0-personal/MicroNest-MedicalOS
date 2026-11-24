"""P1.5: reconcile location_outstanding_summary vs outstanding_for_invoice.

Synthetic dataset covering draft / issued / partial / paid / voided,
multi-allocation, credits, refunds, multi-location, >500 invoices,
and currency quantization.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select

from app.modules.billing import credit_notes as cn
from app.modules.billing import invoices as inv
from app.modules.billing import models as M
from app.modules.billing import payments as pay
from app.modules.billing import refunds as ref
from app.modules.clinics import service as clinics_svc
from tests.helpers import provision_clinical


def _ids(b):
    return {
        "tenant_id": b["tenant"].id,
        "location_id": b["location"].id,
        "patient_id": b["patient"].id,
    }


def _issue(owner_db, b, rate: str):
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


def _pay(owner_db, b, amount: str):
    return pay.create_payment(
        owner_db, actor_id=b["admin"].id, **_ids(b), method="cash", amount=amount
    )


def _alloc(owner_db, b, payment, invoice, amount: str):
    pay.allocate_payment(
        owner_db,
        tenant_id=b["tenant"].id,
        payment_id=payment.id,
        actor_id=b["admin"].id,
        items=[{"invoice_id": invoice.id, "amount": amount}],
    )


def _canonical_open_sum(owner_db, *, tenant_id, location_id) -> tuple[int, Decimal]:
    rows = list(
        owner_db.execute(
            select(M.Invoice).where(
                M.Invoice.tenant_id == tenant_id,
                M.Invoice.location_id == location_id,
                M.Invoice.status.in_((M.INVOICE_ISSUED, M.INVOICE_PARTIALLY_PAID)),
            )
        ).scalars()
    )
    total = Decimal("0.00")
    for invoice in rows:
        total += inv.outstanding_for_invoice(owner_db, invoice=invoice)
    return len(rows), total


def test_outstanding_aggregate_matches_canonical_across_lifecycle(
    owner_db, make_owner_user, make_tenant
):
    b = provision_clinical(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=f"ar-{uuid.uuid4().hex[:6]}",
        admin_email=f"ar-{uuid.uuid4().hex[:6]}@example.com",
    )
    tid, lid = b["tenant"].id, b["location"].id
    actor = b["admin"].id

    # Draft — must not count
    inv.create_invoice(
        owner_db,
        actor_id=actor,
        **_ids(b),
        items=[{"description": "Draft", "quantity": 1, "unit_rate": "999.99"}],
    )

    # Issued unpaid
    issued = _issue(owner_db, b, "100.00")

    # Partially paid (multi-allocation)
    partial = _issue(owner_db, b, "200.00")
    p1 = _pay(owner_db, b, "50.00")
    p2 = _pay(owner_db, b, "30.00")
    _alloc(owner_db, b, p1, partial, "50.00")
    _alloc(owner_db, b, p2, partial, "30.00")

    # Fully paid — excluded from open set
    paid = _issue(owner_db, b, "75.00")
    p_full = _pay(owner_db, b, "75.00")
    _alloc(owner_db, b, p_full, paid, "75.00")

    # Voided after issue with no allocations
    voided = _issue(owner_db, b, "40.00")
    inv.void_invoice(
        owner_db, tenant_id=tid, invoice_id=voided.id, actor_id=actor, reason="test void"
    )

    # Issued + credit note
    credited = _issue(owner_db, b, "90.00")
    note = cn.create_credit_note(
        owner_db,
        tenant_id=tid,
        invoice_id=credited.id,
        actor_id=actor,
        amount="15.00",
        reason="billing error",
    )
    cn.issue_credit_note(owner_db, tenant_id=tid, note_id=note.id, actor_id=actor)

    # Refund of unallocated payment must not change AR
    _pay(owner_db, b, "25.00")
    dangling = _pay(owner_db, b, "10.00")
    ref.create_refund(
        owner_db,
        tenant_id=tid,
        payment_id=dangling.id,
        actor_id=actor,
        amount="10.00",
        reason="duplicate charge",
    )

    # Rounding / precision (quantize half-up)
    precise = _issue(owner_db, b, "33.335")  # stored quantized on create/issue

    # Bulk issued (>500 additional) at 1.00 each
    bulk_n = 510
    for i in range(bulk_n):
        row = inv.create_invoice(
            owner_db,
            actor_id=actor,
            **_ids(b),
            items=[{"description": f"Bulk {i}", "quantity": 1, "unit_rate": "1.00"}],
        )
        inv.issue_invoice(
            owner_db, tenant_id=tid, invoice_id=row.id, actor_id=actor
        )

    # Second location — must not bleed into primary summary
    loc2 = clinics_svc.create_location(
        owner_db,
        tenant=b["tenant"],
        name="Branch B",
        timezone="Asia/Kolkata",
    )
    other = inv.create_invoice(
        owner_db,
        actor_id=actor,
        tenant_id=tid,
        location_id=loc2.id,
        patient_id=b["patient"].id,
        items=[{"description": "Other loc", "quantity": 1, "unit_rate": "500.00"}],
    )
    inv.issue_invoice(owner_db, tenant_id=tid, invoice_id=other.id, actor_id=actor)
    owner_db.commit()

    agg_count, agg_amount = inv.location_outstanding_summary(
        owner_db, tenant_id=tid, location_id=lid
    )
    can_count, can_amount = _canonical_open_sum(
        owner_db, tenant_id=tid, location_id=lid
    )

    assert agg_count == can_count
    assert agg_amount == can_amount
    # Sanity: draft/paid/voided excluded; bulk included
    assert agg_count >= bulk_n + 3  # issued + partial + credited (+ precise)
    assert issued.status == M.INVOICE_ISSUED
    assert partial.status == M.INVOICE_PARTIALLY_PAID
    assert paid.status == M.INVOICE_PAID
    assert voided.status == M.INVOICE_VOIDED
    assert precise.id is not None

    other_count, other_amount = inv.location_outstanding_summary(
        owner_db, tenant_id=tid, location_id=loc2.id
    )
    assert other_count == 1
    assert other_amount == Decimal("500.00")
    assert other_amount != agg_amount


def test_outstanding_no_double_count_allocations(
    owner_db, make_owner_user, make_tenant
):
    b = provision_clinical(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=f"ar2-{uuid.uuid4().hex[:6]}",
        admin_email=f"ar2-{uuid.uuid4().hex[:6]}@example.com",
    )
    invoice = _issue(owner_db, b, "100.00")
    payment = _pay(owner_db, b, "100.00")
    _alloc(owner_db, b, payment, invoice, "40.00")
    _alloc(owner_db, b, payment, invoice, "20.00")
    owner_db.commit()

    expected = inv.outstanding_for_invoice(owner_db, invoice=invoice)
    assert expected == Decimal("40.00")
    count, amount = inv.location_outstanding_summary(
        owner_db, tenant_id=b["tenant"].id, location_id=b["location"].id
    )
    assert count == 1
    assert amount == expected
