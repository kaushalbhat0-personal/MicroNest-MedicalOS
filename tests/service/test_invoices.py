"""Invoice domain (P4.4): drafts, money, issue, numbering, void, conversion.

Covers the locked lifecycle `draft → issued → voided` (P4.5 owns the
payment-driven edges), the at-most-once estimate conversion guard, and
the snapshot independence of issued financial truth.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.modules.billing import estimates as est
from app.modules.billing import invoices as inv
from app.modules.billing import models as M
from app.modules.billing import numbering as numberinglib
from app.modules.billing import service_catalog as catalog
from app.modules.billing.models import Invoice, InvoiceLine
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


def _items(
    rate: str = "100.00", qty: object = 1, **kw: object
) -> list[dict[str, object]]:
    args: dict[str, object] = {
        "description": "Consult",
        "quantity": qty,
        "unit_rate": rate,
    }
    args.update(kw)
    return [args]


def _create(owner_db, b, **kw):  # type: ignore[no-untyped-def]
    args = {"actor_id": b["admin"].id, **_ids(b)}
    args.update(kw)
    return inv.create_invoice(owner_db, **args)


def _issued_estimate(owner_db, b, items):  # type: ignore[no-untyped-def]
    e = est.create_estimate(owner_db, actor_id=b["admin"].id, **_ids(b), items=items)
    return est.issue_estimate(
        owner_db, tenant_id=b["tenant"].id, estimate_id=e.id, actor_id=b["admin"].id
    )


def test_create_draft_computes_totals(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    invoice = _create(
        owner_db,
        b,
        items=[
            {
                "description": "A",
                "quantity": 2,
                "unit_rate": "100.00",
                "tax_rate": "18",
            },
            {"description": "B", "quantity": 1, "unit_rate": "200.00", "tax_rate": "0"},
        ],
    )
    assert invoice.status == M.INVOICE_DRAFT
    assert invoice.doc_number is None and invoice.financial_year is None
    assert invoice.source_estimate_id is None
    lines = inv.invoice_lines(owner_db, invoice_id=invoice.id)
    assert [str(line.line_total) for line in lines] == ["236.00", "200.00"]
    assert str(invoice.subtotal) == "400.00"
    assert str(invoice.tax_total) == "36.00"
    assert str(invoice.grand_total) == "436.00"


def test_money_precision_half_up_and_edges(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    # 3 × 33.33 = 99.99; 2.345% boundary behavior lives in money unit tests;
    # here: discountlarger-than-zero + exempt treatment + zero rate.
    invoice = _create(
        owner_db,
        b,
        items=[
            {
                "description": "paise",
                "quantity": "3",
                "unit_rate": "33.335",
                "discount_amount": "0.01",
                "tax_rate": "18",
                "tax_treatment": "taxable",
            },
            {
                "description": "exempt",
                "quantity": 1,
                "unit_rate": "50.00",
                "tax_rate": "0",
                "tax_treatment": "exempt",
            },
        ],
    )
    lines = inv.invoice_lines(owner_db, invoice_id=invoice.id)
    assert lines[0].taxable_amount == Decimal("100.00")  # 100.005 → HALF_UP
    assert lines[0].tax_amount == Decimal("18.00")
    assert lines[0].line_total == Decimal("118.00")
    assert lines[1].line_total == Decimal("50.00")
    assert invoice.grand_total == Decimal("168.00")
    # Zero-money draft is creatable but unissuable (see issue guards).
    empty = _create(owner_db, b, items=[])
    assert empty.grand_total == Decimal("0.00")
    with pytest.raises(ValidationError):
        inv.issue_invoice(
            owner_db,
            tenant_id=b["tenant"].id,
            invoice_id=empty.id,
            actor_id=b["admin"].id,
        )


def test_catalog_defaults_are_snapshot_only(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    item = catalog.create_service(
        owner_db,
        code=f"inv-{uuid.uuid4().hex[:6]}",
        display="X-Ray",
        default_rate="500.00",
        tax_rate="12",
        hsn_sac="9993",
    )
    invoice = _create(
        owner_db, b, items=[{"service_catalog_id": item.id, "quantity": 1}]
    )
    line = inv.invoice_lines(owner_db, invoice_id=invoice.id)[0]
    assert line.source_estimate_line_id is None
    catalog.update_service(
        owner_db, item_id=item.id, default_rate="9000.00", tax_rate="28"
    )
    owner_db.expire_all()
    assert inv.get_invoice(
        owner_db, tenant_id=b["tenant"].id, invoice_id=invoice.id
    ).grand_total == Decimal("560.00")


def test_draft_editing_and_versioning(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    invoice = _create(owner_db, b, items=_items())
    v0 = invoice.version
    line2 = inv.add_invoice_line(
        owner_db,
        tenant_id=b["tenant"].id,
        invoice_id=invoice.id,
        description="extra",
        quantity=1,
        unit_rate="25.00",
    )
    assert invoice.grand_total == Decimal("125.00") and invoice.version == v0 + 1
    inv.update_invoice_line(
        owner_db, tenant_id=b["tenant"].id, line_id=line2.id, quantity=2
    )
    assert invoice.grand_total == Decimal("150.00")
    inv.remove_invoice_line(owner_db, tenant_id=b["tenant"].id, line_id=line2.id)
    assert invoice.grand_total == Decimal("100.00")
    updated = inv.update_invoice(
        owner_db,
        tenant_id=b["tenant"].id,
        invoice_id=invoice.id,
        notes="pay soon",
        due_date=date(2027, 5, 1),
    )
    assert updated.notes == "pay soon" and str(updated.due_date) == "2027-05-01"
    cleared = inv.update_invoice(
        owner_db,
        tenant_id=b["tenant"].id,
        invoice_id=invoice.id,
        notes=None,
        clear_due_date=True,
    )
    assert cleared.due_date is None


def test_issue_allocates_number_and_freezes(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    invoice = _create(owner_db, b, items=_items("100.00"))
    issued = inv.issue_invoice(
        owner_db,
        tenant_id=b["tenant"].id,
        invoice_id=invoice.id,
        actor_id=b["admin"].id,
    )
    assert issued.status == M.INVOICE_ISSUED
    assert issued.doc_number == 1
    assert issued.financial_year == numberinglib.fy_for(inv._now())
    assert issued.issued_by == b["admin"].id and issued.issued_at is not None
    # Retry is a no-op success: same number, no duplicate.
    again = inv.issue_invoice(
        owner_db,
        tenant_id=b["tenant"].id,
        invoice_id=invoice.id,
        actor_id=b["admin"].id,
    )
    assert again.id == issued.id and again.doc_number == 1
    # Issued financial truth is immutable through every draft writer.
    with pytest.raises(ConflictError):
        inv.update_invoice(
            owner_db, tenant_id=b["tenant"].id, invoice_id=invoice.id, notes="late"
        )
    with pytest.raises(ConflictError):
        inv.add_invoice_line(
            owner_db, tenant_id=b["tenant"].id, invoice_id=invoice.id, description="x"
        )
    line = inv.invoice_lines(owner_db, invoice_id=invoice.id)[0]
    with pytest.raises(ConflictError):
        inv.update_invoice_line(
            owner_db, tenant_id=b["tenant"].id, line_id=line.id, quantity=9
        )
    with pytest.raises(ConflictError):
        inv.remove_invoice_line(owner_db, tenant_id=b["tenant"].id, line_id=line.id)
    with pytest.raises(ConflictError):
        inv.transition_invoice(
            owner_db,
            tenant_id=b["tenant"].id,
            invoice_id=invoice.id,
            to_status=M.INVOICE_PAID,
        )


def test_issue_guards_and_terminal_rules(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    tid = b["tenant"].id
    invoice = _create(owner_db, b, items=_items())
    inv.void_invoice(
        owner_db, tenant_id=tid, invoice_id=invoice.id, actor_id=b["admin"].id
    )
    assert invoice.status == M.INVOICE_VOIDED
    with pytest.raises(ConflictError):
        inv.issue_invoice(
            owner_db, tenant_id=tid, invoice_id=invoice.id, actor_id=b["admin"].id
        )
    with pytest.raises(ValidationError):
        inv.transition_invoice(
            owner_db, tenant_id=tid, invoice_id=invoice.id, to_status="bogus"
        )


def test_void_rules(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    from datetime import datetime, timezone

    from app.platform import ids

    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    tid = b["tenant"].id
    # Draft cancellation is simple (reason optional).
    draft = _create(owner_db, b, items=_items())
    voided_draft = inv.void_invoice(
        owner_db, tenant_id=tid, invoice_id=draft.id, actor_id=b["admin"].id
    )
    assert voided_draft.status == M.INVOICE_VOIDED
    assert voided_draft.voided_by == b["admin"].id
    # Same-state void is a no-op success.
    assert (
        inv.void_invoice(owner_db, tenant_id=tid, invoice_id=draft.id).status
        == M.INVOICE_VOIDED
    )
    # Issued void requires a real reason.
    issued = _create(owner_db, b, items=_items())
    inv.issue_invoice(
        owner_db, tenant_id=tid, invoice_id=issued.id, actor_id=b["admin"].id
    )
    with pytest.raises(ValidationError):
        inv.void_invoice(owner_db, tenant_id=tid, invoice_id=issued.id, reason="x")
    ok = inv.void_invoice(
        owner_db,
        tenant_id=tid,
        invoice_id=issued.id,
        actor_id=b["admin"].id,
        reason="duplicate billing",
    )
    assert ok.status == M.INVOICE_VOIDED and ok.void_reason == "duplicate billing"
    # Paid is terminal: P4.4 never voids it (P4.5 owns corrections).
    paid = _create(owner_db, b, items=_items())
    paid.status = M.INVOICE_PAID
    owner_db.flush()
    with pytest.raises(ConflictError):
        inv.void_invoice(
            owner_db, tenant_id=tid, invoice_id=paid.id, reason="nope nope"
        )
    # Any allocation blocks the void.
    settled = _create(owner_db, b, items=_items())
    inv.issue_invoice(
        owner_db, tenant_id=tid, invoice_id=settled.id, actor_id=b["admin"].id
    )
    now = datetime.now(timezone.utc)
    pay = M.Payment(
        id=ids.uuid7(),
        tenant_id=tid,
        location_id=b["location"].id,
        patient_id=b["patient"].id,
        status=M.PAYMENT_RECORDED,
        amount="100.00",
        currency="INR",
        method="cash",
        received_at=now,
        created_at=now,
        updated_at=now,
    )
    owner_db.add(pay)
    owner_db.flush()
    owner_db.add(
        M.PaymentAllocation(
            id=ids.uuid7(),
            tenant_id=tid,
            patient_id=b["patient"].id,
            payment_id=pay.id,
            invoice_id=settled.id,
            amount="10.00",
            created_at=now,
        )
    )
    owner_db.flush()
    with pytest.raises(ConflictError):
        inv.void_invoice(
            owner_db, tenant_id=tid, invoice_id=settled.id, reason="has allocation"
        )
    # Any credit note blocks the void.
    noted = _create(owner_db, b, items=_items())
    inv.issue_invoice(
        owner_db, tenant_id=tid, invoice_id=noted.id, actor_id=b["admin"].id
    )
    owner_db.add(
        M.CreditNote(
            id=ids.uuid7(),
            tenant_id=tid,
            location_id=b["location"].id,
            patient_id=b["patient"].id,
            invoice_id=noted.id,
            status=M.CREDIT_ISSUED,
            amount="10.00",
            currency="INR",
            reason="adjustment",
            created_at=now,
            updated_at=now,
        )
    )
    owner_db.flush()
    with pytest.raises(ConflictError):
        inv.void_invoice(
            owner_db, tenant_id=tid, invoice_id=noted.id, reason="has credit note"
        )


def test_numbering_series_independence(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    from datetime import datetime, timezone

    from app.modules.clinics import service as clinics_service
    from app.platform import ids

    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    tid = b["tenant"].id
    loc2 = clinics_service.create_location(owner_db, tenant=b["tenant"], name="Annex")
    owner_db.flush()
    first = inv.issue_invoice(
        owner_db,
        tenant_id=tid,
        invoice_id=_create(owner_db, b, items=_items()).id,
        actor_id=b["admin"].id,
    )
    second = inv.issue_invoice(
        owner_db,
        tenant_id=tid,
        invoice_id=_create(owner_db, b, items=_items()).id,
        actor_id=b["admin"].id,
    )
    assert (first.doc_number, second.doc_number) == (1, 2)
    # Independent series per location.
    other_loc = inv.issue_invoice(
        owner_db,
        tenant_id=tid,
        invoice_id=_create(owner_db, b, location_id=loc2.id, items=_items()).id,
        actor_id=b["admin"].id,
    )
    assert other_loc.doc_number == 1
    # Different document types never collide (separate numbered tables).
    now = datetime.now(timezone.utc)
    owner_db.add(
        M.CreditNote(
            id=ids.uuid7(),
            tenant_id=tid,
            location_id=b["location"].id,
            patient_id=b["patient"].id,
            invoice_id=first.id,
            status=M.CREDIT_ISSUED,
            amount="5.00",
            currency="INR",
            reason="series probe",
            financial_year=first.financial_year,
            doc_number=1,
            created_at=now,
            updated_at=now,
        )
    )
    owner_db.flush()  # same integer, different series table: allowed.
    # Gaps are tolerated: a voided invoice keeps its number.
    inv.void_invoice(owner_db, tenant_id=tid, invoice_id=second.id, reason="gap probe")
    third = inv.issue_invoice(
        owner_db,
        tenant_id=tid,
        invoice_id=_create(owner_db, b, items=_items()).id,
        actor_id=b["admin"].id,
    )
    assert third.doc_number == 3


def test_full_estimate_conversion(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    item = catalog.create_service(
        owner_db,
        code=f"cv-{uuid.uuid4().hex[:6]}",
        display="Crown",
        default_rate="1000.00",
        tax_rate="18",
        hsn_sac="9983",
    )
    estimate = _issued_estimate(
        owner_db,
        b,
        items=[
            {"service_catalog_id": item.id, "quantity": 1},
            {
                "description": "X",
                "quantity": 2,
                "unit_rate": "100.00",
                "discount_amount": "10.00",
                "tax_rate": "18",
            },
        ],
    )
    invoice = inv.convert_estimate_to_invoice(
        owner_db,
        tenant_id=b["tenant"].id,
        estimate_id=estimate.id,
        actor_id=b["admin"].id,
    )
    assert invoice.source_estimate_id == estimate.id
    assert invoice.location_id == estimate.location_id
    assert invoice.patient_id == estimate.patient_id
    assert invoice.encounter_id == estimate.encounter_id
    assert invoice.status == M.INVOICE_DRAFT and invoice.doc_number is None
    elines = est.estimate_lines(owner_db, estimate_id=estimate.id)
    ilines = inv.invoice_lines(owner_db, invoice_id=invoice.id)
    assert len(ilines) == 2
    for src, dst in zip(
        sorted(elines, key=lambda e: e.sequence),
        sorted(ilines, key=lambda i: i.sequence),
    ):
        assert dst.source_estimate_line_id == src.id
        assert dst.description == src.description
        assert dst.quantity == src.quantity and dst.unit_rate == src.unit_rate
        assert dst.discount_amount == src.discount_amount
        assert (
            dst.taxable_amount == src.taxable_amount
            and dst.tax_amount == src.tax_amount
        )
        assert dst.tax_rate == src.tax_rate and dst.line_total == src.line_total
        assert dst.hsn_sac == src.hsn_sac and dst.tax_treatment == src.tax_treatment
    assert invoice.grand_total == estimate.grand_total == Decimal("1404.20")
    # Full conversion moves the estimate through the P4.3 writer.
    assert (
        est.get_estimate(
            owner_db, tenant_id=b["tenant"].id, estimate_id=estimate.id
        ).status
        == M.ESTIMATE_CONVERTED
    )


def test_partial_conversion_leaves_estimate_issued(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    estimate = _issued_estimate(
        owner_db,
        b,
        items=[
            {"description": "A", "quantity": 1, "unit_rate": "100.00"},
            {"description": "B", "quantity": 1, "unit_rate": "200.00"},
            {"description": "C", "quantity": 1, "unit_rate": "300.00"},
        ],
    )
    elines = sorted(
        est.estimate_lines(owner_db, estimate_id=estimate.id), key=lambda e: e.sequence
    )
    first = inv.convert_estimate_to_invoice(
        owner_db,
        tenant_id=b["tenant"].id,
        estimate_id=estimate.id,
        actor_id=b["admin"].id,
        line_ids=[elines[0].id, elines[2].id],
        idempotency_key="partial-1",
    )
    got = sorted(
        [
            str(line.line_total)
            for line in inv.invoice_lines(owner_db, invoice_id=first.id)
        ]
    )
    assert got == ["100.00", "300.00"]
    assert first.grand_total == Decimal("400.00")
    # Partial: the estimate stays in its non-terminal state.
    assert (
        est.get_estimate(
            owner_db, tenant_id=b["tenant"].id, estimate_id=estimate.id
        ).status
        == M.ESTIMATE_ISSUED
    )
    # The remainder converts into a second invoice; then the estimate converts.
    second = inv.convert_estimate_to_invoice(
        owner_db,
        tenant_id=b["tenant"].id,
        estimate_id=estimate.id,
        actor_id=b["admin"].id,
        line_ids=[elines[1].id],
    )
    assert second.grand_total == Decimal("200.00")
    assert (
        est.get_estimate(
            owner_db, tenant_id=b["tenant"].id, estimate_id=estimate.id
        ).status
        == M.ESTIMATE_CONVERTED
    )
    # No silent duplicates: the same estimate line never converts twice.
    with pytest.raises(ConflictError):
        inv.convert_estimate_to_invoice(
            owner_db,
            tenant_id=b["tenant"].id,
            estimate_id=estimate.id,
            actor_id=b["admin"].id,
            line_ids=[elines[0].id],
        )
    # The database enforces at-most-once even around the service.
    from datetime import datetime, timezone

    dup = InvoiceLine(
        id=uuid.uuid4(),
        tenant_id=b["tenant"].id,
        invoice_id=second.id,
        source_estimate_line_id=elines[1].id,
        description="dup",
        quantity="1",
        unit_rate="1.00",
        line_total="1.00",
        created_at=datetime.now(timezone.utc),
    )
    owner_db.add(dup)
    with pytest.raises(Exception):
        owner_db.flush()
    owner_db.rollback()


def test_conversion_snapshot_independence(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    item = catalog.create_service(
        owner_db,
        code=f"sn-{uuid.uuid4().hex[:6]}",
        display="Filling",
        default_rate="1000.00",
        tax_rate="18",
    )
    estimate = _issued_estimate(
        owner_db, b, items=[{"service_catalog_id": item.id, "quantity": 1}]
    )
    invoice = inv.convert_estimate_to_invoice(
        owner_db,
        tenant_id=b["tenant"].id,
        estimate_id=estimate.id,
        actor_id=b["admin"].id,
    )
    catalog.update_service(owner_db, item_id=item.id, default_rate="5.00", tax_rate="0")
    owner_db.expire_all()
    line = inv.invoice_lines(owner_db, invoice_id=invoice.id)[0]
    assert line.unit_rate == Decimal("1000.00") and line.tax_rate == Decimal("18")
    assert invoice.grand_total == Decimal("1180.00")


def test_conversion_guards(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    other = provision_clinical(
        owner_db, make_owner_user, make_tenant, slug="conv-guard"
    )
    # Draft estimates cannot convert; only issued proposals convert.
    draft = est.create_estimate(
        owner_db,
        actor_id=b["admin"].id,
        **_ids(b),
        items=[{"description": "A", "quantity": 1, "unit_rate": "10.00"}],
    )
    with pytest.raises(ConflictError):
        inv.convert_estimate_to_invoice(
            owner_db,
            tenant_id=b["tenant"].id,
            estimate_id=draft.id,
            actor_id=b["admin"].id,
        )
    # Cross-tenant source is an oracle miss.
    foreign_est = est.create_estimate(
        owner_db,
        actor_id=other["admin"].id,
        tenant_id=other["tenant"].id,
        location_id=other["location"].id,
        patient_id=other["patient"].id,
        items=[{"description": "A", "quantity": 1, "unit_rate": "10.00"}],
    )
    est.issue_estimate(
        owner_db,
        tenant_id=other["tenant"].id,
        estimate_id=foreign_est.id,
        actor_id=other["admin"].id,
    )
    with pytest.raises(NotFoundError):
        inv.convert_estimate_to_invoice(
            owner_db,
            tenant_id=b["tenant"].id,
            estimate_id=foreign_est.id,
            actor_id=b["admin"].id,
        )
    # A line from another estimate is rejected.
    estimate = _issued_estimate(
        owner_db, b, items=[{"description": "A", "quantity": 1, "unit_rate": "10.00"}]
    )
    other_draft = est.create_estimate(
        owner_db,
        actor_id=b["admin"].id,
        **_ids(b),
        items=[{"description": "Z", "quantity": 1, "unit_rate": "1.00"}],
    )
    alien_line = est.estimate_lines(owner_db, estimate_id=other_draft.id)[0]
    with pytest.raises(ValidationError):
        inv.convert_estimate_to_invoice(
            owner_db,
            tenant_id=b["tenant"].id,
            estimate_id=estimate.id,
            actor_id=b["admin"].id,
            line_ids=[alien_line.id],
        )
    with pytest.raises(NotFoundError):
        inv.convert_estimate_to_invoice(
            owner_db,
            tenant_id=b["tenant"].id,
            estimate_id=estimate.id,
            actor_id=b["admin"].id,
            line_ids=[uuid.uuid4()],
        )
    # Location scope is fail-closed.
    with pytest.raises(ForbiddenError):
        inv.convert_estimate_to_invoice(
            owner_db,
            tenant_id=b["tenant"].id,
            estimate_id=estimate.id,
            actor_id=b["admin"].id,
            location_ids=frozenset({uuid.uuid4()}),
        )


def test_conversion_atomicity(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    estimate = _issued_estimate(
        owner_db, b, items=[{"description": "A", "quantity": 1, "unit_rate": "10.00"}]
    )
    owner_db.commit()
    with pytest.raises(NotFoundError):
        inv.convert_estimate_to_invoice(
            owner_db,
            tenant_id=b["tenant"].id,
            estimate_id=estimate.id,
            actor_id=b["admin"].id,
            line_ids=[uuid.uuid4()],
        )
    owner_db.rollback()
    leftovers = (
        owner_db.execute(
            select(Invoice).where(Invoice.source_estimate_id == estimate.id)
        )
        .scalars()
        .all()
    )
    assert leftovers == []
    assert (
        est.get_estimate(
            owner_db, tenant_id=b["tenant"].id, estimate_id=estimate.id
        ).status
        == M.ESTIMATE_ISSUED
    )


def test_conversion_idempotency(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    from app.modules.patients import service as patients_service

    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    estimate = _issued_estimate(
        owner_db,
        b,
        items=[
            {"description": "A", "quantity": 1, "unit_rate": "100.00"},
            {"description": "B", "quantity": 1, "unit_rate": "50.00"},
        ],
    )
    elines = est.estimate_lines(owner_db, estimate_id=estimate.id)
    first = inv.convert_estimate_to_invoice(
        owner_db,
        tenant_id=b["tenant"].id,
        estimate_id=estimate.id,
        actor_id=b["admin"].id,
        line_ids=[elines[0].id],
        idempotency_key="conv-key-1",
    )
    replay = inv.convert_estimate_to_invoice(
        owner_db,
        tenant_id=b["tenant"].id,
        estimate_id=estimate.id,
        actor_id=b["admin"].id,
        line_ids=[elines[0].id],
        idempotency_key="conv-key-1",
    )
    assert replay.id == first.id
    # Same key, divergent intent → conflict.
    with pytest.raises(ConflictError):
        inv.convert_estimate_to_invoice(
            owner_db,
            tenant_id=b["tenant"].id,
            estimate_id=estimate.id,
            actor_id=b["admin"].id,
            line_ids=[elines[1].id],
            idempotency_key="conv-key-1",
        )
    # Same key against a divergent invoice header → conflict.
    other_patient = patients_service.register_patient(
        owner_db, tenant_id=b["tenant"].id, display_name="Divergent Pat"
    )
    owner_db.flush()
    with pytest.raises(ConflictError):
        inv.create_invoice(
            owner_db,
            actor_id=b["admin"].id,
            tenant_id=b["tenant"].id,
            patient_id=other_patient.id,
            location_id=b["location"].id,
            idempotency_key="conv-key-1",
        )


def test_location_scope_fail_closed(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    scope = frozenset({uuid.uuid4()})
    with pytest.raises(ForbiddenError):
        _create(owner_db, b, location_ids=scope)
    invoice = _create(owner_db, b, items=_items())
    with pytest.raises(ForbiddenError):
        inv.get_invoice(
            owner_db,
            tenant_id=b["tenant"].id,
            invoice_id=invoice.id,
            location_ids=scope,
        )
