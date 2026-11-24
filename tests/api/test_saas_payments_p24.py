"""P2.4 SaaS payment provider — mock HMAC webhooks on real PostgreSQL."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid

from fastapi.testclient import TestClient

from tests.helpers import login_client, provision_tenant, tenant_headers


def _sign(body: bytes, secret: str = "mock-webhook-secret") -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _mock_captured_event(*, order_id: str, amount: int, event_id: str | None = None) -> bytes:
    eid = event_id or f"evt_{uuid.uuid4().hex}"
    payload = {
        "id": eid,
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": f"pay_{uuid.uuid4().hex[:14]}",
                    "order_id": order_id,
                    "amount": amount,
                    "currency": "INR",
                    "status": "captured",
                }
            }
        },
    }
    return json.dumps(payload).encode()


def test_checkout_and_webhook_activates_subscription(
    client, owner_db, make_owner_user, make_tenant
):
    from app.modules.subscriptions import service as subs
    from app.modules.tenancy import service as tenancy_service

    b = provision_tenant(
        owner_db, make_owner_user, make_tenant, slug=f"pay-{uuid.uuid4().hex[:6]}"
    )
    tenancy_service.create_owner(
        owner_db, tenant=b["tenant"], user=b["admin"], created_by=b["admin"]
    )
    owner_db.commit()

    doc = login_client(client, email=b["admin"].email)
    tid = str(b["tenant"].id)
    r = doc.post(
        f"/api/v1/tenants/{tid}/subscription/checkout",
        headers=tenant_headers(tid),
        json={"plan_code": "starter-v1", "idempotency_key": f"idem-{uuid.uuid4().hex}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert body["amount_minor"] == 499900
    assert body["checkout"]["order_id"]
    assert "secret" not in r.text.lower()
    assert "key_secret" not in r.text.lower()
    order_id = body["checkout"]["order_id"]

    # Replay idempotency
    r2 = doc.post(
        f"/api/v1/tenants/{tid}/subscription/checkout",
        headers=tenant_headers(tid),
        json={"plan_code": "starter-v1", "idempotency_key": body["idempotency_key"]},
    )
    assert r2.status_code == 200
    assert r2.json()["id"] == body["id"]

    raw = _mock_captured_event(order_id=order_id, amount=499900)
    wh = client.post(
        "/api/v1/webhooks/saas/mock",
        content=raw,
        headers={"X-SaaS-Signature": _sign(raw), "Content-Type": "application/json"},
    )
    assert wh.status_code == 200, wh.text
    assert wh.json()["status"] == "processed"

    # Duplicate delivery
    wh2 = client.post(
        "/api/v1/webhooks/saas/mock",
        content=raw,
        headers={"X-SaaS-Signature": _sign(raw), "Content-Type": "application/json"},
    )
    assert wh2.status_code == 200
    assert wh2.json()["status"] == "duplicate"

    sub = subs.require_subscription(owner_db, tenant_id=b["tenant"].id)
    owner_db.refresh(sub)
    assert sub.status == "active"
    assert tenancy_service.get_tenant(owner_db, b["tenant"].id).status == "active"

    pays = doc.get(
        f"/api/v1/tenants/{tid}/subscription/payments", headers=tenant_headers(tid)
    ).json()
    assert pays[0]["status"] == "paid"


def test_invalid_signature_rejected(client, owner_db, make_owner_user, make_tenant):
    b = provision_tenant(
        owner_db, make_owner_user, make_tenant, slug=f"sig-{uuid.uuid4().hex[:6]}"
    )
    from app.modules.tenancy import service as tenancy_service

    tenancy_service.create_owner(
        owner_db, tenant=b["tenant"], user=b["admin"], created_by=b["admin"]
    )
    owner_db.commit()
    doc = login_client(client, email=b["admin"].email)
    tid = str(b["tenant"].id)
    checkout = doc.post(
        f"/api/v1/tenants/{tid}/subscription/checkout",
        headers=tenant_headers(tid),
        json={"plan_code": "starter-v1", "idempotency_key": f"idem-{uuid.uuid4().hex}"},
    ).json()
    raw = _mock_captured_event(
        order_id=checkout["checkout"]["order_id"], amount=499900
    )
    bad = client.post(
        "/api/v1/webhooks/saas/mock",
        content=raw,
        headers={"X-SaaS-Signature": "deadbeef", "Content-Type": "application/json"},
    )
    assert bad.status_code == 403


def test_wrong_amount_rejected(client, owner_db, make_owner_user, make_tenant):
    from app.modules.tenancy import service as tenancy_service

    b = provision_tenant(
        owner_db, make_owner_user, make_tenant, slug=f"amt-{uuid.uuid4().hex[:6]}"
    )
    tenancy_service.create_owner(
        owner_db, tenant=b["tenant"], user=b["admin"], created_by=b["admin"]
    )
    owner_db.commit()
    doc = login_client(client, email=b["admin"].email)
    tid = str(b["tenant"].id)
    checkout = doc.post(
        f"/api/v1/tenants/{tid}/subscription/checkout",
        headers=tenant_headers(tid),
        json={"plan_code": "starter-v1", "idempotency_key": f"idem-{uuid.uuid4().hex}"},
    ).json()
    raw = _mock_captured_event(
        order_id=checkout["checkout"]["order_id"], amount=1  # wrong
    )
    wh = client.post(
        "/api/v1/webhooks/saas/mock",
        content=raw,
        headers={"X-SaaS-Signature": _sign(raw), "Content-Type": "application/json"},
    )
    # P2.5: verified receipt is durable; amount conflict → permanent_failure (HTTP 200).
    assert wh.status_code == 200, wh.text
    assert wh.json()["status"] == "permanent_failure"


def test_failed_then_success_out_of_order(
    client, owner_db, make_owner_user, make_tenant
):
    from app.modules.subscriptions import service as subs
    from app.modules.tenancy import service as tenancy_service

    b = provision_tenant(
        owner_db, make_owner_user, make_tenant, slug=f"ord-{uuid.uuid4().hex[:6]}"
    )
    tenancy_service.create_owner(
        owner_db, tenant=b["tenant"], user=b["admin"], created_by=b["admin"]
    )
    owner_db.commit()
    doc = login_client(client, email=b["admin"].email)
    tid = str(b["tenant"].id)
    checkout = doc.post(
        f"/api/v1/tenants/{tid}/subscription/checkout",
        headers=tenant_headers(tid),
        json={"plan_code": "growth-v1", "idempotency_key": f"idem-{uuid.uuid4().hex}"},
    ).json()
    order_id = checkout["checkout"]["order_id"]
    amount = checkout["amount_minor"]

    # Success first
    raw_ok = _mock_captured_event(order_id=order_id, amount=amount, event_id="evt_ok")
    assert (
        client.post(
            "/api/v1/webhooks/saas/mock",
            content=raw_ok,
            headers={"X-SaaS-Signature": _sign(raw_ok)},
        ).status_code
        == 200
    )
    assert subs.require_subscription(owner_db, tenant_id=b["tenant"].id).status == "active"

    # Stale failure must not overwrite
    raw_fail = json.dumps(
        {
            "id": "evt_fail_late",
            "event": "payment.failed",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_fail",
                        "order_id": order_id,
                        "amount": amount,
                        "currency": "INR",
                    }
                }
            },
        }
    ).encode()
    assert (
        client.post(
            "/api/v1/webhooks/saas/mock",
            content=raw_fail,
            headers={"X-SaaS-Signature": _sign(raw_fail)},
        ).status_code
        == 200
    )
    owner_db.expire_all()
    assert subs.require_subscription(owner_db, tenant_id=b["tenant"].id).status == "active"


def test_cross_tenant_checkout_forbidden(
    client, owner_db, make_owner_user, make_tenant
):
    a = provision_tenant(
        owner_db, make_owner_user, make_tenant, slug=f"xa-{uuid.uuid4().hex[:6]}"
    )
    b = provision_tenant(
        owner_db, make_owner_user, make_tenant, slug=f"xb-{uuid.uuid4().hex[:6]}"
    )
    from app.modules.tenancy import service as tenancy_service

    tenancy_service.create_owner(
        owner_db, tenant=a["tenant"], user=a["admin"], created_by=a["admin"]
    )
    owner_db.commit()
    doc = login_client(client, email=a["admin"].email)
    r = doc.post(
        f"/api/v1/tenants/{b['tenant'].id}/subscription/checkout",
        headers=tenant_headers(str(a["tenant"].id)),
        json={"plan_code": "starter-v1", "idempotency_key": f"idem-{uuid.uuid4().hex}"},
    )
    assert r.status_code in (403, 404)


def test_reconcile_platform_only(client, owner_db, make_owner_user, make_tenant):
    from tests.helpers import make_platform_admin

    b = provision_tenant(
        owner_db, make_owner_user, make_tenant, slug=f"rec-{uuid.uuid4().hex[:6]}"
    )
    plat = make_platform_admin(
        owner_db, make_owner_user, email=f"plat-{uuid.uuid4().hex[:6]}@example.com"
    )
    owner_db.commit()
    admin = login_client(client, email=plat.email)
    r = admin.post(f"/api/v1/platform/saas/reconcile/{b['tenant'].id}")
    assert r.status_code == 200, r.text
    assert "findings" in r.json()

    user = login_client(client, email=b["admin"].email)
    assert (
        user.post(f"/api/v1/platform/saas/reconcile/{b['tenant'].id}").status_code
        == 403
    )


def test_browser_return_does_not_activate(client, owner_db, make_owner_user, make_tenant):
    """There is no success callback endpoint that mutates subscription state."""
    b = provision_tenant(
        owner_db, make_owner_user, make_tenant, slug=f"br-{uuid.uuid4().hex[:6]}"
    )
    # Fake "return URL" style POSTs must not exist / must 404/405.
    for path in (
        f"/api/v1/tenants/{b['tenant'].id}/subscription/payment-success",
        "/api/v1/webhooks/saas/mock/browser-return",
    ):
        r = client.post(path, json={"ok": True})
        assert r.status_code in (404, 405, 401, 403)
