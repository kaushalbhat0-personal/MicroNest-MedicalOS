"""Billing P4.1 foundation: schema integrity, isolation, numbering, RLS.

No service layer exists yet — these tests pin the database-level invariants
the future writers must preserve: composite (tenant, patient) allocation
guards, series uniqueness, idempotency keys, money CHECKs, RLS, and the
no-dental-dependency boundary.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.modules.billing import models as B
from app.platform import ids
from tests.helpers import provision_clinical


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _base_ids(b):  # type: ignore[no-untyped-def]
    return {
        "tenant_id": b["tenant"].id,
        "location_id": b["location"].id,
        "patient_id": b["patient"].id,
    }


def _payment(owner_db, **kw):  # type: ignore[no-untyped-def]
    row = B.Payment(
        id=ids.uuid7(),
        status=B.PAYMENT_RECORDED,
        amount=kw.pop("amount", "500.00"),
        currency="INR",
        method="cash",
        received_at=_now(),
        created_at=_now(),
        updated_at=_now(),
        **kw,
    )
    owner_db.add(row)
    owner_db.flush()
    return row


def _invoice(owner_db, **kw):  # type: ignore[no-untyped-def]
    row = B.Invoice(
        id=ids.uuid7(),
        status=B.INVOICE_ISSUED,
        currency="INR",
        subtotal="500.00",
        tax_total="90.00",
        grand_total="590.00",
        financial_year=kw.pop("financial_year", "FY2026-27"),
        doc_number=kw.pop("doc_number", None),
        created_at=_now(),
        updated_at=_now(),
        **kw,
    )
    owner_db.add(row)
    owner_db.flush()
    return row


def test_catalog_is_global_reference(owner_db) -> None:  # type: ignore[no-untyped-def]
    assert "tenant_id" not in B.ServiceCatalogItem.__table__.columns
    row = B.ServiceCatalogItem(
        id=ids.uuid7(), code="CONSULT", display="Consultation", default_rate="500.00"
    )
    owner_db.add(row)
    owner_db.flush()
    assert row.id is not None


def test_cross_patient_allocation_rejected(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from app.modules.patients import service as patients_service

    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    base = _base_ids(b)
    other = patients_service.register_patient(
        owner_db, tenant_id=base["tenant_id"], display_name="Other Pat"
    )
    owner_db.flush()
    pay = _payment(owner_db, **base)
    inv = _invoice(
        owner_db,
        tenant_id=base["tenant_id"],
        location_id=base["location_id"],
        patient_id=other.id,
    )
    with pytest.raises(IntegrityError):
        owner_db.add(
            B.PaymentAllocation(
                id=ids.uuid7(),
                tenant_id=base["tenant_id"],
                patient_id=base["patient_id"],
                payment_id=pay.id,
                invoice_id=inv.id,
                amount="100.00",
                created_at=_now(),
            )
        )
        owner_db.flush()
    owner_db.rollback()


def test_cross_tenant_allocation_rejected(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    a = provision_clinical(owner_db, make_owner_user, make_tenant, slug="bill-a")
    c = provision_clinical(owner_db, make_owner_user, make_tenant, slug="bill-b")
    ia, ic = _base_ids(a), _base_ids(c)
    pay = _payment(owner_db, **ia)
    inv = _invoice(owner_db, **ic)
    with pytest.raises(IntegrityError):
        owner_db.add(
            B.PaymentAllocation(
                id=ids.uuid7(),
                tenant_id=ia["tenant_id"],
                patient_id=ia["patient_id"],
                payment_id=pay.id,
                invoice_id=inv.id,
                amount="50.00",
                created_at=_now(),
            )
        )
        owner_db.flush()
    owner_db.rollback()


def test_refund_receipt_credit_pin_patient(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from app.modules.patients import service as patients_service

    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    base = _base_ids(b)
    other = patients_service.register_patient(
        owner_db, tenant_id=base["tenant_id"], display_name="Other Pat"
    )
    owner_db.flush()
    pay = _payment(owner_db, **base)
    with pytest.raises(IntegrityError):
        owner_db.add(
            B.Refund(
                id=ids.uuid7(),
                tenant_id=base["tenant_id"],
                patient_id=other.id,
                payment_id=pay.id,
                amount="10.00",
                reason="mismatch",
                created_at=_now(),
                updated_at=_now(),
            )
        )
        owner_db.flush()
    owner_db.rollback()
    with pytest.raises(IntegrityError):
        owner_db.add(
            B.Receipt(
                id=ids.uuid7(),
                tenant_id=base["tenant_id"],
                location_id=base["location_id"],
                payment_id=pay.id,
                patient_id=other.id,
                amount="500.00",
                created_at=_now(),
            )
        )
        owner_db.flush()
    owner_db.rollback()


def test_numbering_series_uniqueness(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    base = _base_ids(b)
    _invoice(owner_db, doc_number=7, **base)
    with pytest.raises(IntegrityError):
        _invoice(owner_db, doc_number=7, **base)
    owner_db.rollback()
    # Same number in another FY is a different series.
    _invoice(
        owner_db,
        doc_number=7,
        financial_year="FY2027-28",
        tenant_id=base["tenant_id"],
        location_id=base["location_id"],
        patient_id=base["patient_id"],
    )
    # Drafts without numbers never collide.
    _invoice(owner_db, **base)
    _invoice(owner_db, **base)


def test_idempotency_keys_unique_per_tenant(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    base = _base_ids(b)
    row = B.Estimate(
        id=ids.uuid7(),
        status=B.ESTIMATE_DRAFT,
        idempotency_key="est-key-1",
        created_at=_now(),
        updated_at=_now(),
        **base,
    )
    owner_db.add(row)
    owner_db.flush()
    with pytest.raises(IntegrityError):
        owner_db.add(
            B.Estimate(
                id=ids.uuid7(),
                status=B.ESTIMATE_DRAFT,
                idempotency_key="est-key-1",
                created_at=_now(),
                updated_at=_now(),
                **base,
            )
        )
        owner_db.flush()
    owner_db.rollback()
    # NULL keys are never equal: multiple keyless drafts allowed.
    for _ in range(2):
        owner_db.add(
            B.Estimate(
                id=ids.uuid7(),
                status=B.ESTIMATE_DRAFT,
                created_at=_now(),
                updated_at=_now(),
                **base,
            )
        )
    owner_db.flush()


def test_money_and_content_checks(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    base = _base_ids(b)
    with pytest.raises(IntegrityError):
        _payment(owner_db, amount="-1.00", **base)
    owner_db.rollback()
    with pytest.raises(IntegrityError):
        owner_db.add(
            B.Payment(
                id=ids.uuid7(),
                status=B.PAYMENT_RECORDED,
                amount="10.00",
                currency="USD",
                method="cash",
                received_at=_now(),
                created_at=_now(),
                updated_at=_now(),
                **base,
            )
        )
        owner_db.flush()
    owner_db.rollback()
    inv = _invoice(owner_db, **base)
    with pytest.raises(IntegrityError):
        owner_db.add(
            B.InvoiceLine(
                id=ids.uuid7(),
                tenant_id=base["tenant_id"],
                invoice_id=inv.id,
                description="x",
                quantity="0",
                unit_rate="100.00",
                line_total="0.00",
                created_at=_now(),
            )
        )
        owner_db.flush()
    owner_db.rollback()
    with pytest.raises(IntegrityError):
        owner_db.add(
            B.Refund(
                id=ids.uuid7(),
                tenant_id=base["tenant_id"],
                patient_id=base["patient_id"],
                payment_id=_payment(owner_db, **base).id,
                amount="5.00",
                reason="x",
                created_at=_now(),
                updated_at=_now(),
            )
        )
        owner_db.flush()
    owner_db.rollback()


def test_receipt_is_one_to_one_with_payment(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    base = _base_ids(b)
    pay = _payment(owner_db, **base)
    owner_db.add(
        B.Receipt(
            id=ids.uuid7(),
            tenant_id=base["tenant_id"],
            location_id=base["location_id"],
            payment_id=pay.id,
            patient_id=base["patient_id"],
            amount="500.00",
            created_at=_now(),
        )
    )
    owner_db.flush()
    with pytest.raises(IntegrityError):
        owner_db.add(
            B.Receipt(
                id=ids.uuid7(),
                tenant_id=base["tenant_id"],
                location_id=base["location_id"],
                payment_id=pay.id,
                patient_id=base["patient_id"],
                amount="500.00",
                created_at=_now(),
            )
        )
        owner_db.flush()
    owner_db.rollback()


def test_estimate_plan_reference_is_id_only(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    """treatment_plan_id carries no FK: billing references dental IDs only."""
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    base = _base_ids(b)
    row = B.Estimate(
        id=ids.uuid7(),
        status=B.ESTIMATE_DRAFT,
        treatment_plan_id=uuid.uuid4(),  # random: no dental row required
        created_at=_now(),
        updated_at=_now(),
        **base,
    )
    owner_db.add(row)
    owner_db.flush()
    assert row.treatment_plan_id is not None


def test_no_float_money_columns(owner_db) -> None:  # type: ignore[no-untyped-def]
    import pathlib

    rows = owner_db.execute(
        text(
            "SELECT table_name, column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name IN "
            "('service_catalog','estimates','estimate_lines','invoices','invoice_lines',"
            "'payments','payment_allocations','refunds','credit_notes','receipts') "
            "AND (column_name LIKE '%amount%' OR column_name LIKE '%total%' "
            "OR column_name IN ('default_rate','unit_rate','tax_rate','quantity'))"
        )
    ).fetchall()
    assert rows, "billing money columns missing"
    assert all(r[2] == "numeric" for r in rows), [r for r in rows if r[2] != "numeric"]
    src = pathlib.Path("backend/app/modules/billing/models.py").read_text()
    assert "Float(" not in src
    mig = pathlib.Path("backend/alembic/versions/0009_billing.py").read_text()
    assert "Float(" not in mig


def test_no_billing_module_dependencies() -> None:  # type: ignore[no-untyped-def]
    import pathlib

    for name in ("models.py", "money.py", "numbering.py"):
        src = pathlib.Path(f"backend/app/modules/billing/{name}").read_text()
        for forbidden in (
            "dental",
            "portal",
            "subscription",
            "licensing",
            "scheduling",
        ):
            assert (
                f"from app.modules.{forbidden}" not in src
            ), f"{name} imports {forbidden}"
            assert f"import {forbidden}" not in src, f"{name} imports {forbidden}"


def test_rls_enforced_on_billing_tables(
    owner_db, app_factory, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="bill-rls-a")
    c = provision_clinical(owner_db, make_owner_user, make_tenant, slug="bill-rls-b")
    ia, ic = _base_ids(b), _base_ids(c)
    rows = owner_db.execute(
        text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' AND rowsecurity"
        )
    ).fetchall()
    secured = {r[0] for r in rows}
    for table in (
        "estimates",
        "estimate_lines",
        "invoices",
        "invoice_lines",
        "payments",
        "payment_allocations",
        "refunds",
        "credit_notes",
        "receipts",
    ):
        assert table in secured, f"RLS missing: {table}"
    assert "service_catalog" not in secured
    policies = owner_db.execute(
        text("SELECT tablename FROM pg_policies WHERE schemaname='public'")
    ).fetchall()
    pnames = {r[0] for r in policies}
    assert "invoices" in pnames and "payments" in pnames

    def scoped(session, tenant_id):  # type: ignore[no-untyped-def]
        session.execute(
            text("SELECT set_config('app.tenant_id', :t, false)"), {"t": str(tenant_id)}
        )

    insert = (
        "INSERT INTO invoices (id, tenant_id, location_id, patient_id, status, "
        "currency, subtotal, tax_total, grand_total, created_at, updated_at) "
        "VALUES (gen_random_uuid(), :t, :l, :p, 'draft', 'INR', 0, 0, 0, now(), now())"
    )
    with app_factory() as s:
        import pytest as _pytest

        scoped(s, ic["tenant_id"])
        with _pytest.raises(Exception):
            s.execute(
                text(insert),
                {
                    "t": str(ia["tenant_id"]),
                    "l": str(ic["location_id"]),
                    "p": str(ic["patient_id"]),
                },
            )
            s.commit()
        s.rollback()
        scoped(s, ic["tenant_id"])
        s.execute(
            text(insert),
            {
                "t": str(ic["tenant_id"]),
                "l": str(ic["location_id"]),
                "p": str(ic["patient_id"]),
            },
        )
        s.commit()
        s.rollback()
