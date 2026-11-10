"""O1.3R: read-only subscription & specialty visibility.

Real PostgreSQL via the shared harness. Covers:

- Tenant-facing reads (TENANT_READ-gated, no-oracle preserved).
- Platform reads (platform-admin flag only, bounded pagination).
- Plan catalog integrity (UNIQUE code, idempotent seed, deterministic lookup).
- Specialty readiness (dental ready, ophthalmology discovery-only).
- Billing separation (no shared FKs, trial creates no clinic billing).
- Read-only guarantees (GETs mutate nothing, 405 on write attempts).

Non-goals (asserted absent): enforcement, charges, plan changes, counts.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from tests.helpers import (
    login_client,
    make_platform_admin,
    provision_tenant,
    tenant_headers,
)

BASE_BODY = {
    "clinic_name": "O13R Clinic",
    "slug": "o13r-clinic",
    "location_name": "Main Clinic",
    "timezone": "Asia/Kolkata",
    "specialty_codes": ["dental"],
}


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


# --- Tenant read access ---


def test_tenant_admin_reads_full_subscription_summary(client, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    c, body = _workspace(client, make_owner_user, "o13r-a@example.com")
    tid = body["tenant"]["id"]
    r = c.get(f"/api/v1/tenants/{tid}", headers=tenant_headers(tid))
    assert r.status_code == 200, r.text
    detail = r.json()
    sub = detail["subscription"]
    assert sub["plan_code"] == "trial-14d"
    assert sub["plan_name"] == "Trial (14-day)"
    assert sub["status"] == "trial"
    assert sub["trial_starts_at"] is not None
    assert sub["trial_ends_at"] is not None
    starts = datetime.fromisoformat(sub["trial_starts_at"].replace("Z", "+00:00"))
    ends = datetime.fromisoformat(sub["trial_ends_at"].replace("Z", "+00:00"))
    assert (ends - starts).days == 14
    assert sub["is_in_trial"] is True
    assert sub["limits"] == {
        "max_locations": 3,
        "max_practitioners": 10,
        "max_staff_seats": 25,
        "enforced": False,
    }
    # Specialty detail carries pack version + readiness; the legacy code
    # list stays for backward compatibility.
    assert detail["specialties_enabled"] == ["dental"]
    assert detail["specialties"] == [
        {
            "code": "dental",
            "pack_version": "1.0.0",
            "label": "specialty.dental",
            "maturity": "ready",
            "ready_for_use": True,
        }
    ]


def test_mixed_specialties_represented_with_readiness(client, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    c, body = _workspace(
        client,
        make_owner_user,
        "o13r-b@example.com",
        {"slug": "o13r-mixed", "specialty_codes": ["dental", "ophthalmology"]},
    )
    tid = body["tenant"]["id"]
    detail = c.get(f"/api/v1/tenants/{tid}", headers=tenant_headers(tid)).json()
    assert detail["specialties_enabled"] == ["dental", "ophthalmology"]
    by_code = {s["code"]: s for s in detail["specialties"]}
    assert by_code["dental"]["pack_version"] == "1.0.0"
    assert by_code["dental"]["maturity"] == "ready"
    assert by_code["dental"]["ready_for_use"] is True
    assert by_code["ophthalmology"]["pack_version"] == "0.1.0"
    assert by_code["ophthalmology"]["maturity"] == "discovery"
    assert by_code["ophthalmology"]["ready_for_use"] is False


def test_doctor_and_receptionist_receive_permitted_summary(  # type: ignore[no-untyped-def]
    client, owner_db, make_owner_user, make_tenant
) -> None:
    from app.modules.tenancy import service as tenancy_service

    ctx = provision_tenant(
        owner_db, make_owner_user, make_tenant, admin_email="o13r-boss@example.com"
    )
    tid = str(ctx["tenant"].id)
    doctor = make_owner_user(email="o13r-doc@example.com")
    tenancy_service.create_membership(
        owner_db,
        user=doctor,
        tenant=ctx["tenant"],
        role=tenancy_service.get_seed_role(owner_db, "doctor"),
    )
    recep = make_owner_user(email="o13r-rec@example.com")
    tenancy_service.create_membership(
        owner_db,
        user=recep,
        tenant=ctx["tenant"],
        role=tenancy_service.get_seed_role(owner_db, "receptionist"),
    )
    owner_db.commit()
    for email in ("o13r-doc@example.com", "o13r-rec@example.com"):
        c = login_client(client, email=email)
        r = c.get(f"/api/v1/tenants/{tid}", headers=tenant_headers(tid))
        assert r.status_code == 200, (email, r.text)
        # Permitted summary only: no cost, provider, payment, or secret keys.
        joined = r.text.lower()
        for forbidden in ("card", "charge", "gateway", "provider_ref", "secret", "password"):
            assert forbidden not in joined, (email, forbidden)


def test_role_without_tenant_read_is_denied(  # type: ignore[no-untyped-def]
    client, owner_db, make_owner_user, make_tenant
) -> None:
    from app.modules.tenancy import service as tenancy_service

    ctx = provision_tenant(
        owner_db, make_owner_user, make_tenant, admin_email="o13r-c1@example.com"
    )
    tid = str(ctx["tenant"].id)
    boss = login_client(client, email="o13r-c1@example.com")
    role = boss.post(
        f"/api/v1/tenants/{tid}/roles",
        headers=tenant_headers(tid),
        json={"name": "billing-only", "permissions": ["billing.read"]},
    )
    assert role.status_code == 200, role.text
    clerk = make_owner_user(email="o13r-clerk@example.com")
    from sqlalchemy import select as _select

    from app.modules.tenancy.models import Role as _Role

    custom = owner_db.execute(
        _select(_Role).where(_Role.tenant_id == ctx["tenant"].id, _Role.name == "billing-only")
    ).scalar_one()
    tenancy_service.create_membership(
        owner_db, user=clerk, tenant=ctx["tenant"], role=custom
    )
    owner_db.commit()
    c = login_client(client, email="o13r-clerk@example.com")
    r = c.get(f"/api/v1/tenants/{tid}", headers=tenant_headers(tid))
    assert r.status_code == 403, r.text


def test_member_without_membership_denied(client, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    _, body = _workspace(client, make_owner_user, "o13r-d@example.com", {"slug": "o13r-d"})
    tid = body["tenant"]["id"]
    make_owner_user(email="o13r-stranger@example.com")
    stranger = login_client(client, email="o13r-stranger@example.com")
    assert (
        stranger.get(f"/api/v1/tenants/{tid}", headers=tenant_headers(tid)).status_code
        == 403
    )


def test_cross_tenant_reads_blocked_without_oracle(client, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    c1, b1 = _workspace(client, make_owner_user, "o13r-e1@example.com", {"slug": "o13r-e1"})
    c2, b2 = _workspace(client, make_owner_user, "o13r-e2@example.com", {"slug": "o13r-e2"})
    t1, t2 = b1["tenant"]["id"], b2["tenant"]["id"]
    # Forged selector for a foreign tenant: fail-closed, no data.
    assert c1.get(f"/api/v1/tenants/{t2}", headers=tenant_headers(t2)).status_code == 403
    # Valid selector but foreign path id: 404 anti-oracle (not 403).
    assert c1.get(f"/api/v1/tenants/{t2}", headers=tenant_headers(t1)).status_code == 404
    # Forged selector never resolves, even when the path is the caller's own.
    assert c1.get(f"/api/v1/tenants/{t1}", headers=tenant_headers(t2)).status_code == 403
    # Unknown id with a valid selector: 404, indistinguishable from foreign.
    assert (
        c1.get(
            "/api/v1/tenants/00000000-0000-4000-8000-000000000000",
            headers=tenant_headers(t1),
        ).status_code
        == 404
    )
    # Neither probe leaks the other tenant's subscription.
    r = c1.get(f"/api/v1/tenants/{t2}", headers=tenant_headers(t1))
    assert "trial-14d" not in r.text


def test_expired_and_suspended_trials_do_not_gate_reads(  # type: ignore[no-untyped-def]
    client, owner_db, make_owner_user
) -> None:
    """Non-enforcement guarantee: commercial state never changes clinical
    read availability. Reads behave identically for expired/suspended rows."""
    c, body = _workspace(
        client, make_owner_user, "o13r-f@example.com", {"slug": "o13r-f"}
    )
    tid = body["tenant"]["id"]
    owner_db.execute(
        text("UPDATE subscriptions SET trial_ends_at = now() - interval '1 day' WHERE tenant_id = :t"),
        {"t": tid},
    )
    owner_db.commit()
    r = c.get(f"/api/v1/tenants/{tid}", headers=tenant_headers(tid))
    assert r.status_code == 200, r.text
    assert r.json()["subscription"]["is_in_trial"] is False
    assert (
        c.get(f"/api/v1/tenants/{tid}/locations", headers=tenant_headers(tid)).status_code
        == 200
    )
    owner_db.execute(
        text("UPDATE subscriptions SET status = 'suspended' WHERE tenant_id = :t"),
        {"t": tid},
    )
    owner_db.commit()
    r = c.get(f"/api/v1/tenants/{tid}", headers=tenant_headers(tid))
    assert r.status_code == 200, r.text
    assert r.json()["subscription"]["status"] == "suspended"
    assert r.json()["subscription"]["is_in_trial"] is False
    assert (
        c.get(f"/api/v1/tenants/{tid}/locations", headers=tenant_headers(tid)).status_code
        == 200
    )


# --- Platform read access ---


def test_platform_list_and_detail(  # type: ignore[no-untyped-def]
    client, owner_db, make_owner_user
) -> None:
    _, b1 = _workspace(client, make_owner_user, "o13r-h1@example.com", {"slug": "o13r-h1"})
    _, b2 = _workspace(
        client,
        make_owner_user,
        "o13r-h2@example.com",
        {"slug": "o13r-h2", "specialty_codes": ["ophthalmology"]},
    )
    make_platform_admin(owner_db, make_owner_user, email="o13r-plat@example.com")
    plat = login_client(client, email="o13r-plat@example.com")
    r = plat.get("/api/v1/platform/tenants?limit=50")
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["total"] >= 2
    assert payload["limit"] == 50 and payload["offset"] == 0
    by_slug = {i["slug"]: i for i in payload["items"]}
    assert {"o13r-h1", "o13r-h2"} <= set(by_slug)
    item = by_slug["o13r-h1"]
    assert item["subscription"]["plan_code"] == "trial-14d"
    assert item["subscription"]["plan_name"] == "Trial (14-day)"
    assert item["subscription"]["is_in_trial"] is True
    assert item["subscription"]["limits"]["enforced"] is False
    assert item["specialties_enabled"] == ["dental"]
    assert by_slug["o13r-h2"]["specialties"][0]["maturity"] == "discovery"
    assert by_slug["o13r-h2"]["specialties"][0]["ready_for_use"] is False
    assert "created_at" in item and "updated_at" in item
    # No clinical / patient / billing / secret surface.
    joined = r.text.lower()
    for forbidden in (
        "patient", "invoice", "payment", "diagnosis", "prescription",
        "password", "secret", "token", "phone", "email",
    ):
        assert forbidden not in joined, forbidden
    # Detail view for one workspace.
    d = plat.get(f"/api/v1/platform/tenants/{b1['tenant']['id']}")
    assert d.status_code == 200, d.text
    assert d.json()["slug"] == "o13r-h1"
    assert d.json()["subscription"]["plan_code"] == "trial-14d"
    assert d.json()["specialties_enabled"] == ["dental"]
    joined = d.text.lower()
    for forbidden in ("patient", "invoice", "payment", "password", "secret", "token"):
        assert forbidden not in joined, forbidden
    # Unknown tenant is 404.
    assert (
        plat.get("/api/v1/platform/tenants/00000000-0000-4000-8000-000000000000").status_code
        == 404
    )


def test_platform_denies_non_admin_and_anonymous(client, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    _, body = _workspace(client, make_owner_user, "o13r-i@example.com", {"slug": "o13r-i"})
    tid = body["tenant"]["id"]
    c = login_client(client, email="o13r-i@example.com")
    assert c.get("/api/v1/platform/tenants").status_code == 403
    assert c.get(f"/api/v1/platform/tenants/{tid}").status_code == 403
    assert client.get("/api/v1/platform/tenants").status_code == 401
    assert (
        client.get(f"/api/v1/platform/tenants/{tid}").status_code == 401
    )


def test_platform_pagination_and_status_filter(  # type: ignore[no-untyped-def]
    client, owner_db, make_owner_user
) -> None:
    for i in range(3):
        _workspace(
            client, make_owner_user, f"o13r-p{i}@example.com", {"slug": f"o13r-p{i}"}
        )
    make_platform_admin(owner_db, make_owner_user, email="o13r-pp@example.com")
    plat = login_client(client, email="o13r-pp@example.com")
    first = plat.get("/api/v1/platform/tenants?limit=1&offset=0").json()
    second = plat.get("/api/v1/platform/tenants?limit=1&offset=1").json()
    assert first["total"] >= 3 and first["limit"] == 1 and first["offset"] == 0
    assert len(first["items"]) == 1 and len(second["items"]) == 1
    assert first["items"][0]["id"] != second["items"][0]["id"]
    assert plat.get("/api/v1/platform/tenants?status=active").status_code == 200
    assert plat.get("/api/v1/platform/tenants?status=bogus").status_code == 422
    assert plat.get("/api/v1/platform/tenants?limit=0").status_code == 422
    assert plat.get("/api/v1/platform/tenants?limit=101").status_code == 422


def test_platform_reads_mutate_nothing(client, owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    """O1.4R amendment: commercial tables stay immutable; platform reads now
    append the expected `platform.tenant.*` audit events (one per viewed
    tenant — see test_o14r_console.py). The no-write-methods assertion below
    is unchanged."""
    _, body = _workspace(client, make_owner_user, "o13r-j@example.com", {"slug": "o13r-j"})
    make_platform_admin(owner_db, make_owner_user, email="o13r-pj@example.com")
    plat = login_client(client, email="o13r-pj@example.com")

    def _counts():  # type: ignore[no-untyped-def]
        tables = ["tenants", "subscriptions", "subscription_plans", "tenant_specialties"]
        return {
            t: owner_db.execute(select(func.count()).select_from(text(t))).scalar_one()
            for t in tables
        }

    def _audit_count() -> int:  # type: ignore[no-untyped-def]
        return owner_db.execute(
            select(func.count())
            .select_from(text("audit_events"))
            .where(text("action LIKE 'platform.tenant.%'"))
        ).scalar_one()

    before = _counts()
    audit_before = _audit_count()
    n_listed = plat.get("/api/v1/platform/tenants?limit=100").json()["total"]
    assert plat.get(f"/api/v1/platform/tenants/{body['tenant']['id']}").status_code == 200
    assert _counts() == before
    assert _audit_count() == audit_before + n_listed + 1
    # No write method exists on the read views.
    assert plat.post("/api/v1/platform/tenants/" + body["tenant"]["id"]).status_code in (404, 405)
    assert plat.patch(f"/api/v1/platform/tenants/{body['tenant']['id']}", json={}).status_code in (404, 405)
    assert plat.delete(f"/api/v1/platform/tenants/{body['tenant']['id']}").status_code in (404, 405)


def test_platform_list_legacy_tenant_without_subscription(  # type: ignore[no-untyped-def]
    client, owner_db, make_owner_user, make_tenant
) -> None:
    ctx = provision_tenant(
        owner_db, make_owner_user, make_tenant,
        slug="o13r-legacy", admin_email="o13r-leg@example.com",
    )
    make_platform_admin(owner_db, make_owner_user, email="o13r-pl@example.com")
    plat = login_client(client, email="o13r-pl@example.com")
    d = plat.get(f"/api/v1/platform/tenants/{ctx['tenant'].id}")
    assert d.status_code == 200, d.text
    assert d.json()["subscription"] is None
    assert d.json()["specialties_enabled"] == []


# --- Plan catalog integrity ---


def test_trial_plan_code_is_unique(owner_db) -> None:  # type: ignore[no-untyped-def]
    rows = owner_db.execute(
        text(
            "SELECT count(*) FROM pg_constraint WHERE conname = 'subscription_plans_code_key'"
        )
    ).scalar_one()
    assert rows == 1
    from sqlalchemy.exc import IntegrityError

    from app.platform.db import Base  # noqa: F401  (keeps metadata importable)
    from app.modules.subscriptions.models import SubscriptionPlan

    from datetime import datetime, timezone

    owner_db.add(
        SubscriptionPlan(
            id=uuid.uuid4(),
            code="trial-14d",
            name="Duplicate",
            max_locations=1,
            max_practitioners=1,
            max_staff_seats=1,
            trial_days=14,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    with pytest.raises(IntegrityError):
        owner_db.flush()
    owner_db.rollback()


def test_repeated_seed_execution_creates_no_duplicates(owner_db) -> None:  # type: ignore[no-untyped-def]
    seed = (
        "INSERT INTO subscription_plans "
        "(id, code, name, max_locations, max_practitioners, max_staff_seats, "
        " trial_days, is_active, created_at, updated_at) "
        "VALUES (gen_random_uuid(), 'trial-14d', 'Trial (14-day)', "
        " 3, 10, 25, 14, true, now(), now()) "
        "ON CONFLICT (code) DO NOTHING"
    )
    owner_db.execute(text(seed))
    owner_db.execute(text(seed))
    owner_db.commit()
    n = owner_db.execute(
        text("SELECT count(*) FROM subscription_plans WHERE code = 'trial-14d'")
    ).scalar_one()
    assert n == 1


def test_plan_lookup_is_deterministic(owner_db) -> None:  # type: ignore[no-untyped-def]
    from app.modules.subscriptions import service as subs

    first = subs.get_plan_by_code(owner_db, code="trial-14d")
    second = subs.get_plan_by_code(owner_db, code="trial-14d")
    assert first.id == second.id
    trial = subs.get_trial_plan(owner_db)
    assert trial.code == "trial-14d" and trial.is_active is True
    with pytest.raises(Exception):
        subs.get_plan_by_code(owner_db, code="no-such-plan")


def test_inactive_or_missing_plan_fails_safely(owner_db) -> None:  # type: ignore[no-untyped-def]
    from app.modules.subscriptions import service as subs
    from app.platform.errors import NotFoundError

    owner_db.execute(
        text("UPDATE subscription_plans SET is_active = false WHERE code = 'trial-14d'")
    )
    owner_db.flush()
    with pytest.raises(NotFoundError):
        subs.get_trial_plan(owner_db)
    owner_db.rollback()


def test_provisioning_still_creates_exactly_one_trial(  # type: ignore[no-untyped-def]
    client, owner_db, make_owner_user
) -> None:
    _, body = _workspace(client, make_owner_user, "o13r-k@example.com", {"slug": "o13r-k"})
    n = owner_db.execute(
        text("SELECT count(*) FROM subscriptions WHERE tenant_id = :t"),
        {"t": body["tenant"]["id"]},
    ).scalar_one()
    assert n == 1


# --- Specialty readiness ---


def test_specialty_readiness_values(client, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    from app.modules.workspaces import registry

    assert registry.SPECIALTIES["dental"].maturity == "ready"
    assert registry.SPECIALTIES["dental"].version == "1.0.0"
    assert registry.SPECIALTIES["ophthalmology"].maturity == "discovery"
    assert registry.SPECIALTIES["ophthalmology"].version == "0.1.0"
    c, body = _workspace(
        client,
        make_owner_user,
        "o13r-l@example.com",
        {"slug": "o13r-l", "specialty_codes": ["ophthalmology"]},
    )
    detail = c.get(
        f"/api/v1/tenants/{body['tenant']['id']}",
        headers=tenant_headers(body["tenant"]["id"]),
    ).json()
    (eye,) = detail["specialties"]
    assert eye["maturity"] == "discovery"
    assert eye["ready_for_use"] is False
    # The read model exposes readiness metadata only — no workflow
    # affordances, no clinical catalogs, no authorization hints.
    assert set(eye) == {"code", "pack_version", "label", "maturity", "ready_for_use"}


def test_unknown_specialty_fails_safe() -> None:
    from app.modules.workspaces import registry

    described = registry.describe_specialty("cardiology", "9.9.9")
    assert described["maturity"] == "unknown"
    assert described["ready_for_use"] is False
    assert described["pack_version"] == "9.9.9"


def test_specialty_does_not_change_authorization(  # type: ignore[no-untyped-def]
    client, make_owner_user
) -> None:
    """An ophthalmology-only workspace authorizes exactly like a dental one:
    specialty metadata is display-only."""
    c, body = _workspace(
        client,
        make_owner_user,
        "o13r-m@example.com",
        {"slug": "o13r-m", "specialty_codes": ["ophthalmology"]},
    )
    tid = body["tenant"]["id"]
    assert c.get(f"/api/v1/tenants/{tid}", headers=tenant_headers(tid)).status_code == 200
    assert (
        c.get(f"/api/v1/tenants/{tid}/locations", headers=tenant_headers(tid)).status_code
        == 200
    )


# --- Billing separation ---


BILLING_TABLES = [
    "estimates",
    "invoices",
    "payments",
    "payment_allocations",
    "receipts",
    "refunds",
    "credit_notes",
]


def test_trial_creates_no_clinic_billing_rows(  # type: ignore[no-untyped-def]
    client, owner_db, make_owner_user
) -> None:
    _, body = _workspace(client, make_owner_user, "o13r-n@example.com", {"slug": "o13r-n"})
    tid = body["tenant"]["id"]
    for table in BILLING_TABLES:
        n = owner_db.execute(
            text(f"SELECT count(*) FROM {table} WHERE tenant_id = :t"), {"t": tid}
        ).scalar_one()
        assert n == 0, table


def test_no_cross_ledger_foreign_keys(owner_db) -> None:  # type: ignore[no-untyped-def]
    fks = owner_db.execute(
        text(
            "SELECT tc.table_name, kcu.column_name, ccu.table_name AS ref_table "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON tc.constraint_name = kcu.constraint_name "
            "JOIN information_schema.constraint_column_usage ccu "
            "  ON tc.constraint_name = ccu.constraint_name "
            "WHERE tc.constraint_type = 'FOREIGN KEY'"
        )
    ).all()
    by_table: dict[str, set[str]] = {}
    for table, _col, ref in fks:
        by_table.setdefault(table, set()).add(ref)
    subscription_tables = {"subscriptions", "subscription_plans"}
    clinic_tables = {
        "invoices", "invoice_lines", "payments", "payment_allocations",
        "receipts", "refunds", "credit_notes", "estimates", "estimate_lines",
        "patients", "encounters", "portal_links",
    }
    for table in subscription_tables:
        assert not (by_table.get(table, set()) & clinic_tables), (table, by_table.get(table))
    for table in (
        "invoices", "payments", "payment_allocations", "receipts", "refunds",
        "credit_notes", "estimates", "portal_links",
    ):
        assert not (by_table.get(table, set()) & subscription_tables), (table, by_table.get(table))
    # No patient-subscription SKU exists anywhere.
    tables = owner_db.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    ).all()
    names = {r[0] for r in tables}
    assert "patient_subscriptions" not in names
    assert "subscription_invoices" not in names
    assert "subscription_payments" not in names
    plans = owner_db.execute(text("SELECT code FROM subscription_plans")).all()
    assert [r[0] for r in plans] == ["trial-14d"]


def test_portal_enrollment_needs_no_subscription(  # type: ignore[no-untyped-def]
    client, owner_db, make_owner_user, make_tenant
) -> None:
    """Legacy (subscription-less) tenants enroll portal users normally:
    portal access is not gated on any subscription."""
    from app.modules.patients import service as patients_service

    ctx = provision_tenant(
        owner_db, make_owner_user, make_tenant,
        slug="o13r-portal", admin_email="o13r-po@example.com",
    )
    tid = str(ctx["tenant"].id)
    patient = patients_service.register_patient(
        owner_db, tenant_id=ctx["tenant"].id, display_name="Portal Kid"
    )
    owner_db.commit()
    boss = login_client(client, email="o13r-po@example.com")
    r = boss.post(
        f"/api/v1/tenants/{tid}/portal-links",
        headers=tenant_headers(tid),
        json={"email": "portal-kid@example.com", "patient_id": str(patient.id)},
    )
    assert r.status_code == 200, r.text


def test_subscription_responses_carry_no_billing_records(  # type: ignore[no-untyped-def]
    client, owner_db, make_owner_user
) -> None:
    _, body = _workspace(client, make_owner_user, "o13r-o@example.com", {"slug": "o13r-o"})
    tid = body["tenant"]["id"]
    c = login_client(client, email="o13r-o@example.com")
    tenant_detail = c.get(f"/api/v1/tenants/{tid}", headers=tenant_headers(tid))
    assert tenant_detail.status_code == 200
    for forbidden in ("invoice", "payment", "allocation", "receipt", "refund", "credit_note", "card", "charge", "gateway"):
        assert forbidden not in tenant_detail.text.lower(), forbidden
    make_platform_admin(owner_db, make_owner_user, email="o13r-q@example.com")
    plat = login_client(client, email="o13r-q@example.com")
    listed = plat.get("/api/v1/platform/tenants?limit=100")
    assert listed.status_code == 200
    for forbidden in ("invoice", "payment", "allocation", "receipt", "refund", "credit_note", "card", "charge", "gateway"):
        assert forbidden not in listed.text.lower(), forbidden
