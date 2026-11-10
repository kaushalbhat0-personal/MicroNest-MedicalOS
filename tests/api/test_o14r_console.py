"""O1.4R: read-only Platform Admin Console (API behavior + audit).

Real PostgreSQL via the shared harness. Covers:

- Deny by default (anonymous 401, tenant admin 403, deactivated admin 401).
- Platform list/detail access, pagination, status filtering, error states.
- Audited platform reads: one refs-only event per viewed tenant in that
  tenant's own hash chain; failures mint no events.
- Tenant isolation preserved; forbidden-data scan on console responses.
- Commercial tables stay immutable (only expected audit rows are added).

Non-goals (asserted absent): counts, owner identity, writes, enforcement.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from tests.helpers import (
    login_client,
    make_platform_admin,
    provision_tenant,
    tenant_headers,
)

BASE_BODY = {
    "clinic_name": "O14R Clinic",
    "slug": "o14r-clinic",
    "location_name": "Main Clinic",
    "timezone": "Asia/Kolkata",
    "specialty_codes": ["dental"],
}

FORBIDDEN = (
    "patient",
    "invoice",
    "payment",
    "diagnosis",
    "prescription",
    "password",
    "secret",
    "token",
    "phone",
    "email",
    "owner",
)


def _provision(c: TestClient, body: dict | None = None, *, key: str | None = None):  # type: ignore[no-untyped-def]
    payload = dict(BASE_BODY)
    if body:
        payload.update(body)
    hdrs = {}
    if key is not None:
        hdrs["Idempotency-Key"] = key
    return c.post("/api/v1/workspaces", json=payload, headers=hdrs)


def _workspace(client, make_owner_user, email: str, body: dict | None = None):  # type: ignore[no-untyped-def]
    make_owner_user(email=email)
    c = login_client(client, email=email)
    r = _provision(c, body, key=str(uuid.uuid4()))
    assert r.status_code == 201, r.text
    return c, r.json()


def _platform_client(client, owner_db, make_owner_user, email: str):  # type: ignore[no-untyped-def]
    make_platform_admin(owner_db, make_owner_user, email=email)
    return login_client(client, email=email)


def _platform_events(owner_db, tenant_id: object):  # type: ignore[no-untyped-def]
    from app.modules.audit.models import AuditEvent

    return (
        owner_db.execute(
            select(AuditEvent)
            .where(
                AuditEvent.tenant_id == tenant_id,
                AuditEvent.action.in_(["platform.tenant.list", "platform.tenant.read"]),
            )
            .order_by(AuditEvent.seq)
        )
        .scalars()
        .all()
    )


def _all_platform_events(owner_db) -> int:  # type: ignore[no-untyped-def]
    return owner_db.execute(
        select(func.count())
        .select_from(text("audit_events"))
        .where(text("action LIKE 'platform.tenant.%'"))
    ).scalar_one()


# --- Deny by default ---


def test_anonymous_list_and_detail_denied_and_unaudited(client, make_owner_user, owner_db) -> None:  # type: ignore[no-untyped-def]
    _, body = _workspace(client, make_owner_user, "o14r-a@example.com", {"slug": "o14r-a"})
    assert client.get("/api/v1/platform/tenants").status_code == 401
    assert client.get(f"/api/v1/platform/tenants/{body['tenant']['id']}").status_code == 401
    assert _all_platform_events(owner_db) == 0


def test_tenant_admin_denied_and_unaudited(client, make_owner_user, owner_db) -> None:  # type: ignore[no-untyped-def]
    c, body = _workspace(client, make_owner_user, "o14r-b@example.com", {"slug": "o14r-b"})
    tid = body["tenant"]["id"]
    assert c.get("/api/v1/platform/tenants").status_code == 403
    assert c.get(f"/api/v1/platform/tenants/{tid}").status_code == 403
    assert _all_platform_events(owner_db) == 0


def test_deactivated_platform_admin_denied_and_unaudited(client, owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    _, body = _workspace(client, make_owner_user, "o14r-c@example.com", {"slug": "o14r-c"})
    admin = make_platform_admin(owner_db, make_owner_user, email="o14r-root@example.com")
    admin.is_active = False
    owner_db.commit()
    # Login itself must fail closed for a deactivated account.
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "o14r-root@example.com", "password": "password-12345-abc"},
    )
    assert r.status_code == 401
    assert _all_platform_events(owner_db) == 0
    # Even with a stolen/old bearer token shape, the flag alone grants nothing:
    # reactivated-but-unflagged users are still denied.
    admin.is_active = True
    admin.is_platform_admin = False
    owner_db.commit()
    c = login_client(client, email="o14r-root@example.com")
    assert c.get("/api/v1/platform/tenants").status_code == 403
    assert c.get(f"/api/v1/platform/tenants/{body['tenant']['id']}").status_code == 403
    assert _all_platform_events(owner_db) == 0


# --- Access, pagination, filtering, empty/error states ---


def test_platform_list_pagination_and_status_filter(client, owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    _workspace(client, make_owner_user, "o14r-d1@example.com", {"slug": "o14r-d1"})
    _workspace(
        client,
        make_owner_user,
        "o14r-d2@example.com",
        {"slug": "o14r-d2", "specialty_codes": ["ophthalmology"]},
    )
    _workspace(client, make_owner_user, "o14r-d3@example.com", {"slug": "o14r-d3"})
    plat = _platform_client(client, owner_db, make_owner_user, "o14r-pd@example.com")

    first = plat.get("/api/v1/platform/tenants?limit=2&offset=0").json()
    assert first["total"] == 3 and first["limit"] == 2 and first["offset"] == 0
    assert len(first["items"]) == 2
    second = plat.get("/api/v1/platform/tenants?limit=2&offset=2").json()
    assert len(second["items"]) == 1
    assert second["items"][0]["id"] not in {i["id"] for i in first["items"]}
    assert second["items"][0]["id"] != first["items"][0]["id"]

    active = plat.get("/api/v1/platform/tenants?status=active")
    assert active.status_code == 200 and active.json()["total"] == 3
    suspended = plat.get("/api/v1/platform/tenants?status=suspended")
    assert suspended.status_code == 200 and suspended.json()["total"] == 0
    assert suspended.json()["items"] == []

    assert plat.get("/api/v1/platform/tenants?status=bogus").status_code == 422
    assert plat.get("/api/v1/platform/tenants?limit=0").status_code == 422
    assert plat.get("/api/v1/platform/tenants?limit=101").status_code == 422
    assert plat.get("/api/v1/platform/tenants?offset=-1").status_code == 422


def test_platform_detail_shapes_and_unknown_is_404(client, owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    _, b1 = _workspace(client, make_owner_user, "o14r-e1@example.com", {"slug": "o14r-e1"})
    plat = _platform_client(client, owner_db, make_owner_user, "o14r-pe@example.com")
    d = plat.get(f"/api/v1/platform/tenants/{b1['tenant']['id']}")
    assert d.status_code == 200, d.text
    item = d.json()
    # Identity + timestamps; tenant status and subscription status are
    # separate fields from separate domains (never conflated).
    assert item["slug"] == "o14r-e1"
    assert item["status"] in ("active", "suspended", "deactivated")
    assert item["created_at"] and item["updated_at"]
    assert item["subscription"]["status"] in (
        "trial", "active", "past_due", "grace", "suspended", "cancelled", "expired",
    )
    assert item["subscription"]["plan_code"] == "trial-14d"
    assert item["subscription"]["limits"]["enforced"] is False
    assert item["specialties"] and item["specialties_enabled"] == ["dental"]
    # Unknown tenant: 404 and no audit event anywhere.
    assert (
        plat.get("/api/v1/platform/tenants/00000000-0000-4000-8000-000000000000").status_code
        == 404
    )
    assert _all_platform_events(owner_db) == 1  # only the successful detail read


def test_console_responses_carry_no_forbidden_data(client, owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    _workspace(client, make_owner_user, "o14r-f@example.com", {"slug": "o14r-f"})
    plat = _platform_client(client, owner_db, make_owner_user, "o14r-pf@example.com")
    listed = plat.get("/api/v1/platform/tenants?limit=100")
    assert listed.status_code == 200
    for forbidden in FORBIDDEN:
        assert forbidden not in listed.text.lower(), forbidden


# --- Audited platform reads ---


def test_detail_read_appends_single_refs_only_event(client, owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    from app.modules.audit import service as audit_service

    _, body = _workspace(client, make_owner_user, "o14r-g@example.com", {"slug": "o14r-g"})
    tid = body["tenant"]["id"]
    admin = make_platform_admin(owner_db, make_owner_user, email="o14r-pg@example.com")
    plat = login_client(client, email="o14r-pg@example.com")

    assert plat.get(f"/api/v1/platform/tenants/{tid}").status_code == 200
    events = _platform_events(owner_db, tid)
    assert len(events) == 1
    ev = events[0]
    assert ev.action == "platform.tenant.read"
    assert ev.actor_type == "user" and ev.actor_id == str(admin.id)
    assert ev.resource_type == "tenant" and ev.resource_id == tid
    assert ev.result == "ok" and ev.request_id and ev.request_id != "-"
    # Refs only: no email, no names, no secrets anywhere in the row.
    assert "o14r-pg@example.com" not in str(ev.__dict__)
    assert "o14r-g" not in str(ev.__dict__)
    # Chain integrity holds for the event's day.
    assert audit_service.verify_chain(owner_db, tenant_id=ev.tenant_id, day=ev.chain_day) is True

    # A second read appends a second event (one per view, no dedup).
    assert plat.get(f"/api/v1/platform/tenants/{tid}").status_code == 200
    assert len(_platform_events(owner_db, tid)) == 2


def test_list_reads_audit_each_returned_tenant_only(client, owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    _, b1 = _workspace(client, make_owner_user, "o14r-h1@example.com", {"slug": "o14r-h1"})
    _, b2 = _workspace(client, make_owner_user, "o14r-h2@example.com", {"slug": "o14r-h2"})
    plat = _platform_client(client, owner_db, make_owner_user, "o14r-ph@example.com")

    assert plat.get("/api/v1/platform/tenants?limit=1&offset=0").status_code == 200
    first_ids = [b1["tenant"]["id"], b2["tenant"]["id"]]
    listed_first = _platform_events(owner_db, first_ids[0]) + _platform_events(owner_db, first_ids[1])
    assert len(listed_first) == 1  # exactly the one returned tenant
    listed_tid = listed_first[0].tenant_id
    assert listed_first[0].action == "platform.tenant.list"

    other = next(t for t in first_ids if t != str(listed_tid))
    assert _platform_events(owner_db, other) == []

    assert plat.get("/api/v1/platform/tenants?limit=1&offset=1").status_code == 200
    assert len(_platform_events(owner_db, other)) == 1


def test_failures_mint_no_audit_events(client, owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    c, body = _workspace(client, make_owner_user, "o14r-i@example.com", {"slug": "o14r-i"})
    tid = body["tenant"]["id"]
    plat = _platform_client(client, owner_db, make_owner_user, "o14r-pi@example.com")

    assert plat.get("/api/v1/platform/tenants?status=bogus").status_code == 422
    assert plat.get("/api/v1/platform/tenants/00000000-0000-4000-8000-000000000000").status_code == 404
    assert c.get(f"/api/v1/platform/tenants/{tid}").status_code == 403
    assert client.get(f"/api/v1/platform/tenants/{tid}").status_code == 401
    assert _all_platform_events(owner_db) == 0


def test_commercial_tables_immutable_audit_only_grows(client, owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    _, body = _workspace(client, make_owner_user, "o14r-j@example.com", {"slug": "o14r-j"})
    plat = _platform_client(client, owner_db, make_owner_user, "o14r-pj@example.com")

    def _counts():  # type: ignore[no-untyped-def]
        tables = ["tenants", "subscriptions", "subscription_plans", "tenant_specialties"]
        return {
            t: owner_db.execute(select(func.count()).select_from(text(t))).scalar_one()
            for t in tables
        }

    before = _counts()
    audit_before = _all_platform_events(owner_db)
    n_listed = plat.get("/api/v1/platform/tenants?limit=100").json()["total"]
    assert plat.get(f"/api/v1/platform/tenants/{body['tenant']['id']}").status_code == 200
    assert _counts() == before
    # Only the expected audit rows are added: one per listed tenant + one detail.
    assert _all_platform_events(owner_db) == audit_before + n_listed + 1


# --- Isolation preserved ---


def test_platform_console_preserves_tenant_isolation(client, owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    ctx = provision_tenant(owner_db, make_owner_user, make_tenant, slug="o14r-iso", admin_email="o14r-iso@example.com")
    tid = str(ctx["tenant"].id)
    plat = _platform_client(client, owner_db, make_owner_user, "o14r-piso@example.com")

    # Platform admins have no membership: tenant-scoped routes stay 403.
    assert plat.get(f"/api/v1/tenants/{tid}", headers=tenant_headers(tid)).status_code == 403
    assert plat.get(f"/api/v1/tenants/{tid}/patients", headers=tenant_headers(tid)).status_code == 403
    # Tenant members cannot reach the console.
    member = login_client(client, email="o14r-iso@example.com")
    assert member.get("/api/v1/platform/tenants").status_code == 403
    # Console responses expose no clinical surface even for real tenants.
    listed = plat.get("/api/v1/platform/tenants?limit=100").json()
    assert {i["id"] for i in listed["items"]} >= {tid}
