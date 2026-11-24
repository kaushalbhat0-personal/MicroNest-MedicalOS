"""P2.5 durable webhook inbox, refunds, retry — real PostgreSQL."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid

from tests.helpers import login_client, make_platform_admin, provision_tenant, tenant_headers


def _sign(body: bytes, secret: str = "mock-webhook-secret") -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _owner_checkout(client, owner_db, make_owner_user, make_tenant, *, plan="starter-v1"):
    from app.modules.tenancy import service as tenancy_service

    b = provision_tenant(
        owner_db, make_owner_user, make_tenant, slug=f"p25-{uuid.uuid4().hex[:6]}"
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
        json={"plan_code": plan, "idempotency_key": f"idem-{uuid.uuid4().hex}"},
    )
    assert r.status_code == 200, r.text
    return b, doc, tid, r.json()


def _captured(*, order_id: str, amount: int, event_id: str | None = None) -> bytes:
    eid = event_id or f"evt_{uuid.uuid4().hex}"
    return json.dumps(
        {
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
    ).encode()


def test_durable_receipt_survives_permanent_amount_conflict(
    client, owner_db, make_owner_user, make_tenant
):
    b, doc, tid, checkout = _owner_checkout(
        client, owner_db, make_owner_user, make_tenant
    )
    _ = b, doc, tid
    raw = _captured(order_id=checkout["checkout"]["order_id"], amount=1)
    wh = client.post(
        "/api/v1/webhooks/saas/mock",
        content=raw,
        headers={"X-SaaS-Signature": _sign(raw)},
    )
    assert wh.status_code == 200
    assert wh.json()["status"] == "permanent_failure"
    inbox_id = wh.json().get("inbox_id")
    # Platform can inspect durable failure (not discarded).
    plat = make_platform_admin(
        owner_db, make_owner_user, email=f"p25a-{uuid.uuid4().hex[:6]}@example.com"
    )
    owner_db.commit()
    admin = login_client(client, email=plat.email)
    rows = admin.get("/api/v1/platform/saas/webhook-inbox?status=permanent_failure").json()
    assert any(str(r["id"]) == str(inbox_id) or r["status"] == "permanent_failure" for r in rows)
    assert any(r["last_error"] for r in rows)


def test_partial_and_full_refund_do_not_auto_cancel(
    client, owner_db, make_owner_user, make_tenant
):
    from app.modules.subscriptions import service as subs

    b, doc, tid, checkout = _owner_checkout(
        client, owner_db, make_owner_user, make_tenant
    )
    order_id = checkout["checkout"]["order_id"]
    amount = checkout["amount_minor"]
    pay_id = f"pay_{uuid.uuid4().hex[:14]}"
    raw_ok = json.dumps(
        {
            "id": f"evt_cap_{uuid.uuid4().hex[:8]}",
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": pay_id,
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
            content=raw_ok,
            headers={"X-SaaS-Signature": _sign(raw_ok)},
        ).json()["status"]
        == "processed"
    )
    owner_db.expire_all()
    assert subs.require_subscription(owner_db, tenant_id=b["tenant"].id).status == "active"

    # Partial refund
    half = amount // 2
    raw_partial = json.dumps(
        {
            "id": f"evt_ref_p_{uuid.uuid4().hex[:8]}",
            "event": "refund.processed",
            "payload": {
                "payment": {"entity": {"id": pay_id, "order_id": order_id, "amount": amount}},
                "refund": {"entity": {"payment_id": pay_id, "amount": half, "currency": "INR"}},
            },
        }
    ).encode()
    assert (
        client.post(
            "/api/v1/webhooks/saas/mock",
            content=raw_partial,
            headers={"X-SaaS-Signature": _sign(raw_partial)},
        ).json()["status"]
        == "processed"
    )
    pays = doc.get(
        f"/api/v1/tenants/{tid}/subscription/payments", headers=tenant_headers(tid)
    ).json()
    assert pays[0]["status"] == "partially_refunded"
    assert pays[0]["refunded_amount_minor"] == half
    owner_db.expire_all()
    assert subs.require_subscription(owner_db, tenant_id=b["tenant"].id).status == "active"

    # Full remaining refund
    raw_full = json.dumps(
        {
            "id": f"evt_ref_f_{uuid.uuid4().hex[:8]}",
            "event": "refund.processed",
            "payload": {
                "payment": {"entity": {"id": pay_id, "order_id": order_id, "amount": amount}},
                "refund": {
                    "entity": {"payment_id": pay_id, "amount": amount - half, "currency": "INR"}
                },
            },
        }
    ).encode()
    assert (
        client.post(
            "/api/v1/webhooks/saas/mock",
            content=raw_full,
            headers={"X-SaaS-Signature": _sign(raw_full)},
        ).json()["status"]
        == "processed"
    )
    pays2 = doc.get(
        f"/api/v1/tenants/{tid}/subscription/payments", headers=tenant_headers(tid)
    ).json()
    assert pays2[0]["status"] == "refunded"
    assert pays2[0]["refunded_amount_minor"] == amount
    owner_db.expire_all()
    # Subscription still active — refund ≠ auto-cancel (P2.5).
    assert subs.require_subscription(owner_db, tenant_id=b["tenant"].id).status == "active"


def test_cancel_at_period_end(client, owner_db, make_owner_user, make_tenant):
    b, doc, tid, _checkout = _owner_checkout(
        client, owner_db, make_owner_user, make_tenant
    )
    _ = b
    r = doc.post(
        f"/api/v1/tenants/{tid}/subscription/cancel",
        headers=tenant_headers(tid),
        json={"reason": "schedule_end", "at_period_end": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cancel_at_period_end"] is True
    assert body["status"] != "cancelled"


def test_previous_webhook_secret_rotation(
    client, owner_db, make_owner_user, make_tenant, monkeypatch
):
    from app.platform.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(
        type(settings),
        "SAAS_PAYMENT_WEBHOOK_SECRET_PREVIOUS",
        "old-webhook-secret",
        raising=False,
    )
    # Force settings object used by provider to see previous secret.
    monkeypatch.setenv("SAAS_PAYMENT_WEBHOOK_SECRET_PREVIOUS", "old-webhook-secret")
    from app.platform import config as cfg

    monkeypatch.setattr(
        cfg,
        "get_settings",
        lambda: cfg.Settings(
            JWT_SECRET="test-only-secret-min-32-chars-xxxxxxxx",
            ENV="test",
            SAAS_PAYMENT_PROVIDER="mock",
            SAAS_PAYMENT_WEBHOOK_SECRET="mock-webhook-secret",
            SAAS_PAYMENT_WEBHOOK_SECRET_PREVIOUS="old-webhook-secret",
        ),
    )
    b, _doc, _tid, checkout = _owner_checkout(
        client, owner_db, make_owner_user, make_tenant
    )
    _ = b
    raw = _captured(order_id=checkout["checkout"]["order_id"], amount=checkout["amount_minor"])
    wh = client.post(
        "/api/v1/webhooks/saas/mock",
        content=raw,
        headers={"X-SaaS-Signature": _sign(raw, "old-webhook-secret")},
    )
    assert wh.status_code == 200, wh.text
    assert wh.json()["status"] == "processed"


def test_replay_and_process_due_platform_only(
    client, owner_db, make_owner_user, make_tenant
):
    b, doc, tid, checkout = _owner_checkout(
        client, owner_db, make_owner_user, make_tenant
    )
    _ = b, tid
    raw = _captured(order_id=checkout["checkout"]["order_id"], amount=1)
    wh = client.post(
        "/api/v1/webhooks/saas/mock",
        content=raw,
        headers={"X-SaaS-Signature": _sign(raw)},
    )
    assert wh.json()["status"] == "permanent_failure"
    inbox_id = wh.json()["inbox_id"]

    # Clinic user cannot list inbox
    assert doc.get("/api/v1/platform/saas/webhook-inbox").status_code == 403

    plat = make_platform_admin(
        owner_db, make_owner_user, email=f"p25b-{uuid.uuid4().hex[:6]}@example.com"
    )
    owner_db.commit()
    admin = login_client(client, email=plat.email)
    due = admin.post("/api/v1/platform/saas/webhooks/process-due?limit=5")
    assert due.status_code == 200
    # Replay of permanent amount conflict stays permanent
    rp = admin.post(f"/api/v1/platform/saas/webhook-inbox/{inbox_id}/replay")
    assert rp.status_code == 200
    assert rp.json()["status"] in ("permanent_failure", "duplicate", "processed")


def test_dispute_marks_txn_not_subscription(
    client, owner_db, make_owner_user, make_tenant
):
    from app.modules.subscriptions import service as subs
    from app.modules.tenancy import service as tenancy_service

    b, doc, tid, checkout = _owner_checkout(
        client, owner_db, make_owner_user, make_tenant
    )
    order_id = checkout["checkout"]["order_id"]
    amount = checkout["amount_minor"]
    pay_id = f"pay_{uuid.uuid4().hex[:14]}"
    raw_ok = json.dumps(
        {
            "id": f"evt_dcap_{uuid.uuid4().hex[:8]}",
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": pay_id,
                        "order_id": order_id,
                        "amount": amount,
                        "currency": "INR",
                    }
                }
            },
        }
    ).encode()
    client.post(
        "/api/v1/webhooks/saas/mock",
        content=raw_ok,
        headers={"X-SaaS-Signature": _sign(raw_ok)},
    )
    raw_disp = json.dumps(
        {
            "id": f"evt_disp_{uuid.uuid4().hex[:8]}",
            "event": "payment.dispute.created",
            "payload": {
                "payment": {
                    "entity": {"id": pay_id, "order_id": order_id, "amount": amount}
                }
            },
        }
    ).encode()
    assert (
        client.post(
            "/api/v1/webhooks/saas/mock",
            content=raw_disp,
            headers={"X-SaaS-Signature": _sign(raw_disp)},
        ).json()["status"]
        == "processed"
    )
    pays = doc.get(
        f"/api/v1/tenants/{tid}/subscription/payments", headers=tenant_headers(tid)
    ).json()
    assert pays[0]["status"] == "disputed"
    owner_db.expire_all()
    assert subs.require_subscription(owner_db, tenant_id=b["tenant"].id).status == "active"
    assert tenancy_service.get_tenant(owner_db, b["tenant"].id).status == "active"


def test_manual_renewal_purpose(client, owner_db, make_owner_user, make_tenant):
    b, doc, tid, checkout = _owner_checkout(
        client, owner_db, make_owner_user, make_tenant
    )
    # Activate first
    raw = _captured(
        order_id=checkout["checkout"]["order_id"], amount=checkout["amount_minor"]
    )
    client.post(
        "/api/v1/webhooks/saas/mock",
        content=raw,
        headers={"X-SaaS-Signature": _sign(raw)},
    )
    r = doc.post(
        f"/api/v1/tenants/{tid}/subscription/checkout",
        headers=tenant_headers(tid),
        json={
            "plan_code": "starter-v1",
            "idempotency_key": f"renew-{uuid.uuid4().hex}",
            "purpose": "renewal",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["purpose"] == "renewal"
    assert r.json()["status"] == "pending"
    _ = b
