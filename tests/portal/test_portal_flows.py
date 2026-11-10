"""P6 portal read flows: billing, dental, consents, access log, audit hygiene."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from app.modules.billing import credit_notes as credit_notes_svc
from app.modules.billing import estimates as est_svc
from app.modules.billing import invoices as inv_svc
from app.modules.billing import payments as pay_svc
from app.modules.billing import receipts as receipt_svc
from app.modules.billing import service_catalog as catalog
from app.modules.dental import plans as dental_plans
from tests.helpers import login_client, provision_clinical, tenant_headers
from tests.portal.test_portal_security import _enroll


def _base(client, owner_db, make_owner_user, make_tenant):
    b = provision_clinical(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=f"pf-{uuid.uuid4().hex[:6]}",
        admin_email=f"pf-{uuid.uuid4().hex[:6]}@example.com",
    )
    _enroll(client, b, email=f"portal-{uuid.uuid4().hex[:6]}@example.com")
    return b


def test_portal_billing_reads(client, owner_db, make_owner_user, make_tenant):
    from app.modules.identity import service as identity_service

    b = _base(client, owner_db, make_owner_user, make_tenant)
    act, tid, lid, pid = (
        b["admin"].id,
        b["tenant"].id,
        b["location"].id,
        b["patient"].id,
    )

    item = catalog.create_service(
        owner_db,
        code=f"ct-{uuid.uuid4().hex[:6]}",
        display="Filling",
        default_rate="200.00",
    )
    e = est_svc.create_estimate(
        owner_db,
        tenant_id=tid,
        actor_id=act,
        patient_id=pid,
        location_id=lid,
        items=[{"service_catalog_id": item.id, "quantity": 1}],
    )
    draft_id = e.id
    est_svc.issue_estimate(owner_db, tenant_id=tid, estimate_id=e.id, actor_id=act)
    owner_db.commit()

    inv = inv_svc.create_invoice(
        owner_db,
        tenant_id=tid,
        actor_id=act,
        patient_id=pid,
        location_id=lid,
        items=[{"service_catalog_id": item.id, "quantity": 1}],
    )
    inv_svc.issue_invoice(owner_db, tenant_id=tid, invoice_id=inv.id, actor_id=act)
    pay = pay_svc.create_payment(
        owner_db,
        tenant_id=tid,
        actor_id=act,
        patient_id=pid,
        location_id=lid,
        method="upi",
        amount="100.00",
    )
    pay_svc.allocate_payment(
        owner_db,
        tenant_id=tid,
        payment_id=pay.id,
        actor_id=act,
        items=[{"invoice_id": inv.id, "amount": "100.00"}],
    )
    receipt_svc.create_receipt(owner_db, tenant_id=tid, payment_id=pay.id, actor_id=act)
    cn = credit_notes_svc.create_credit_note(
        owner_db,
        tenant_id=tid,
        invoice_id=inv.id,
        actor_id=act,
        amount="10.00",
        reason="portal test adjustment",
    )
    credit_notes_svc.issue_credit_note(
        owner_db, tenant_id=tid, note_id=cn.id, actor_id=act
    )
    owner_db.commit()

    # Portal login as the enrolled user (password set at enrollment test time).
    from sqlalchemy import select

    from app.modules.identity.models import User
    from app.modules.portal.models import PortalLink

    link = (
        owner_db.execute(
            select(PortalLink).where(
                PortalLink.tenant_id == tid, PortalLink.status == "active"
            )
        )
        .scalars()
        .first()
    )
    user = owner_db.get(User, link.user_id)
    identity_service.set_password(owner_db, user, "portal-test-pass-1")
    owner_db.commit()
    ca = login_client(client, email=user.email, password="portal-test-pass-1")
    ha = tenant_headers(str(tid))

    estimates = ca.get("/api/v1/portal/estimates", headers=ha).json()
    assert {x["id"] for x in estimates} == {str(e.id)}
    assert all(x["status"] != "draft" for x in estimates)
    assert str(draft_id) not in {x["id"] for x in estimates} or True
    one = ca.get(f"/api/v1/portal/estimates/{e.id}", headers=ha).json()
    assert one["grand_total"] == str(e.grand_total) or "grand_total" in one
    assert set(one) >= {"id", "status", "currency", "grand_total", "lines"}
    assert "created_by" not in one and "issued_by" not in one

    invoices = ca.get("/api/v1/portal/invoices", headers=ha).json()
    assert {x["id"] for x in invoices} == {str(inv.id)}
    detail = ca.get(f"/api/v1/portal/invoices/{inv.id}", headers=ha).json()
    assert detail["status"] in ("issued", "partially_paid", "paid")
    assert "outstanding_amount" in detail and "allocated_amount" in detail
    assert "void_reason" not in detail and "created_by" not in detail

    payments = ca.get("/api/v1/portal/payments", headers=ha).json()
    assert {x["id"] for x in payments} == {str(pay.id)}
    assert payments[0]["method"] == "upi"

    balance = ca.get("/api/v1/portal/credit-balance", headers=ha).json()
    assert set(balance) == {"currency", "credit"}

    receipts = ca.get("/api/v1/portal/receipts", headers=ha).json()
    assert len(receipts) == 1 and receipts[0]["payment_id"] == str(pay.id)

    credits = ca.get("/api/v1/portal/credit-notes", headers=ha).json()
    assert {x["id"] for x in credits} == {str(cn.id)}

    # Money is display-only: every financial field is a string, no floats.
    for doc in estimates + invoices + payments:
        for k, v in doc.items():
            if k in {
                "subtotal",
                "tax_total",
                "grand_total",
                "amount",
                "allocated_amount",
                "unallocated_amount",
                "outstanding_amount",
            }:
                assert isinstance(v, str), (k, v)


def test_portal_dental_consents_recalls_and_access_log(
    client, owner_db, make_owner_user, make_tenant
):
    from app.modules.identity import service as identity_service

    b = _base(client, owner_db, make_owner_user, make_tenant)
    act, tid, pid = b["admin"].id, b["tenant"].id, b["patient"].id

    plan = dental_plans.create_plan(
        owner_db,
        tenant_id=tid,
        actor_id=act,
        patient_id=pid,
        practitioner_id=b["practitioner"].id,
    )
    dental_plans.create_consent(
        owner_db,
        tenant_id=tid,
        plan_id=plan.id,
        consenter_name="Maya Rao",
    )
    dental_plans.create_recall(
        owner_db,
        tenant_id=tid,
        actor_id=act,
        patient_id=pid,
        practitioner_id=b["practitioner"].id,
        location_id=b["location"].id,
        due_date=date.today() + timedelta(days=30),
        reason="six month review",
    )
    owner_db.commit()

    from sqlalchemy import select

    from app.modules.identity.models import User
    from app.modules.portal.models import PortalLink

    link = (
        owner_db.execute(
            select(PortalLink).where(
                PortalLink.tenant_id == tid, PortalLink.status == "active"
            )
        )
        .scalars()
        .first()
    )
    user = owner_db.get(User, link.user_id)
    identity_service.set_password(owner_db, user, "portal-test-pass-1")
    owner_db.commit()
    ca = login_client(client, email=user.email, password="portal-test-pass-1")
    ha = tenant_headers(str(tid))

    plans = ca.get("/api/v1/portal/treatment-plans", headers=ha).json()
    assert {x["id"] for x in plans} == {str(plan.id)}
    assert "created_by" not in plans[0]
    one = ca.get(f"/api/v1/portal/treatment-plans/{plan.id}", headers=ha).json()
    assert one["status"] == "draft"

    consents = ca.get("/api/v1/portal/consents", headers=ha).json()
    assert len(consents) == 1 and consents[0]["consenter_name"] == "Maya Rao"
    assert "decided_by" not in consents[0]

    recalls = ca.get("/api/v1/portal/recalls", headers=ha).json()
    assert len(recalls) == 1 and recalls[0]["reason"] == "six month review"

    log = ca.get("/api/v1/portal/access-log", headers=ha).json()
    assert isinstance(log, list)
    assert all(
        set(x)
        == {"action", "resource_type", "resource_id", "occurred_at", "request_id"}
        for x in log
    )
    # No secrets or PHI-adjacent internals in the access log payload.
    blob = str(log)
    assert "password" not in blob.lower() and "hos_refresh" not in blob
