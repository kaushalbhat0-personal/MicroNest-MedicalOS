"""P2.1 entitlement shadow evaluation — never enforces."""

from __future__ import annotations

import uuid

from tests.helpers import (
    login_client,
    make_platform_admin,
    provision_scheduling,
    provision_tenant,
    tenant_headers,
)


def _ensure_sub(owner_db, tenant):
    from app.modules.subscriptions import service as subs

    if subs.get_subscription(owner_db, tenant_id=tenant.id) is None:
        subs.create_trial_subscription(owner_db, tenant=tenant)
        owner_db.commit()


def test_entitlements_resolve_trial_plan_and_usage(
    client, owner_db, make_owner_user, make_tenant
):
    b = provision_scheduling(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=f"ent-{uuid.uuid4().hex[:6]}",
        admin_email=f"ent-{uuid.uuid4().hex[:6]}@example.com",
    )
    _ensure_sub(owner_db, b["tenant"])
    doc = login_client(client, email=b["admin"].email)
    h = tenant_headers(str(b["tenant"].id))
    r = doc.get(f"/api/v1/tenants/{b['tenant'].id}/entitlements", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["evaluation_mode"] == "enforced"
    assert body["enforcement_active"] is True
    assert "max_staff_seats" in body["enforced_keys"]
    assert body["subscription"]["status"] == "trial"
    assert body["plan"]["code"] == "trial-14d"
    assert body["features"]["patient_portal"] is True
    assert body["features"]["inventory"] is True  # trial evaluation SKU (P2.3)
    assert body["usage"]["max_locations"]["available"] is True
    assert body["usage"]["max_locations"]["value"] >= 1
    assert body["usage"]["max_staff_seats"]["value"] >= 1
    assert body["usage"]["max_practitioners"]["value"] >= 1
    assert body["usage"]["max_storage_bytes"]["available"] is False
    by_key = {e["key"]: e for e in body["evaluations"]}
    assert by_key["patient_portal"]["result"] == "allowed"
    assert by_key["inventory"]["result"] == "allowed"  # trial evaluation features
    assert by_key["max_locations"]["result"] == "allowed"
    # No clinic AR / clinical payload fields on entitlement summary.
    for forbidden in ("invoice_id", "encounter_id", "diagnosis", "prescription"):
        assert forbidden not in r.text.lower()
    assert "patient_id" not in r.text.lower()
    assert "display_name" not in r.text.lower()


def test_cross_tenant_entitlements_isolated(
    client, owner_db, make_owner_user, make_tenant
):
    a = provision_tenant(
        owner_db, make_owner_user, make_tenant, slug=f"ea-{uuid.uuid4().hex[:6]}"
    )
    b = provision_tenant(
        owner_db, make_owner_user, make_tenant, slug=f"eb-{uuid.uuid4().hex[:6]}"
    )
    _ensure_sub(owner_db, a["tenant"])
    _ensure_sub(owner_db, b["tenant"])
    doc = login_client(client, email=a["admin"].email)
    r = doc.get(
        f"/api/v1/tenants/{b['tenant'].id}/entitlements",
        headers=tenant_headers(str(a["tenant"].id)),
    )
    assert r.status_code in (403, 404)


def test_patient_cannot_read_entitlements(
    client, owner_db, make_owner_user, make_tenant
):
    from app.modules.identity import service as identity_service
    from app.modules.tenancy import service as tenancy_service

    b = provision_tenant(
        owner_db, make_owner_user, make_tenant, slug=f"ep-{uuid.uuid4().hex[:6]}"
    )
    _ensure_sub(owner_db, b["tenant"])
    patient_user = identity_service.create_user(
        owner_db,
        email=f"epat-{uuid.uuid4().hex[:6]}@example.com",
        display_name="Portal",
        password="password-12345-abc",
    )
    tenancy_service.create_membership(
        owner_db,
        user=patient_user,
        tenant=b["tenant"],
        role=tenancy_service.get_seed_role(owner_db, "patient"),
    )
    owner_db.commit()
    pat = login_client(client, email=patient_user.email)
    r = pat.get(
        f"/api/v1/tenants/{b['tenant'].id}/entitlements",
        headers=tenant_headers(str(b["tenant"].id)),
    )
    assert r.status_code == 403


def test_subscription_inactive_shadow_and_no_mutation(
    client, owner_db, make_owner_user, make_tenant
):
    from app.modules.subscriptions import service as subs
    from app.modules.tenancy import service as tenancy_service

    b = provision_tenant(
        owner_db, make_owner_user, make_tenant, slug=f"ei-{uuid.uuid4().hex[:6]}"
    )
    _ensure_sub(owner_db, b["tenant"])
    plat = make_platform_admin(
        owner_db, make_owner_user, email=f"eplat-{uuid.uuid4().hex[:6]}@example.com"
    )
    owner_db.commit()
    plat_c = login_client(client, email=plat.email)
    tid = b["tenant"].id
    before_status = tenancy_service.get_tenant(owner_db, tid).status
    assert (
        plat_c.post(
            f"/api/v1/tenants/{tid}/subscription/transition",
            json={"status": "suspended", "note": "shadow test"},
        ).status_code
        == 200
    )
    doc = login_client(client, email=b["admin"].email)
    body = doc.get(
        f"/api/v1/tenants/{tid}/entitlements", headers=tenant_headers(str(tid))
    ).json()
    assert body["subscription"]["status"] == "suspended"
    assert body["subscription"]["commercially_usable"] is False
    assert body["enforcement_active"] is True
    by_key = {e["key"]: e for e in body["evaluations"]}
    assert by_key["patient_portal"]["result"] == "subscription_inactive"
    assert by_key["max_staff_seats"]["result"] == "subscription_inactive"
    # Abuse axis untouched; GET did not mutate subscription further
    assert tenancy_service.get_tenant(owner_db, tid).status == before_status
    sub = subs.require_subscription(owner_db, tenant_id=tid)
    assert sub.status == "suspended"


def test_would_exceed_limit_on_increment(
    client, owner_db, make_owner_user, make_tenant
):
    from app.modules.subscriptions import service as subs

    b = provision_tenant(
        owner_db, make_owner_user, make_tenant, slug=f"ex-{uuid.uuid4().hex[:6]}"
    )
    _ensure_sub(owner_db, b["tenant"])
    # Starter allows 1 location; tenant already has Main Clinic
    plat = make_platform_admin(
        owner_db, make_owner_user, email=f"explat-{uuid.uuid4().hex[:6]}@example.com"
    )
    owner_db.commit()
    plat_c = login_client(client, email=plat.email)
    assert (
        plat_c.post(
            f"/api/v1/tenants/{b['tenant'].id}/subscription/assign-plan",
            json={"plan_code": "starter-v1"},
        ).status_code
        == 200
    )
    doc = login_client(client, email=b["admin"].email)
    body = doc.get(
        f"/api/v1/tenants/{b['tenant'].id}/entitlements",
        headers=tenant_headers(str(b["tenant"].id)),
    ).json()
    assert body["plan"]["code"] == "starter-v1"
    assert body["limits"]["max_locations"] == 1
    assert body["usage"]["max_locations"]["value"] >= 1
    by_key = {e["key"]: e for e in body["evaluations"]}
    assert by_key["max_locations"]["result"] == "allowed"
    assert by_key["max_locations__increment"]["result"] == "would_exceed_limit"
    assert by_key["max_locations__increment"]["would_deny_if_enforced"] is True
    # P2.2: creating a location is blocked when at capacity.
    from app.modules.clinics import service as clinics_svc
    from app.platform.errors import EntitlementExceededError
    import pytest

    with pytest.raises(EntitlementExceededError):
        clinics_svc.create_location(
            owner_db, tenant=b["tenant"], name=f"Extra {uuid.uuid4().hex[:4]}"
        )
    owner_db.rollback()
    assert subs.require_subscription(owner_db, tenant_id=b["tenant"].id).status == "active"


def test_missing_subscription_and_growth_features(owner_db, make_owner_user, make_tenant):
    from sqlalchemy import delete

    from app.modules.subscriptions import entitlements as ent
    from app.modules.subscriptions import service as subs
    from app.modules.subscriptions.models import Subscription

    b = provision_tenant(
        owner_db, make_owner_user, make_tenant, slug=f"em-{uuid.uuid4().hex[:6]}"
    )
    owner_db.execute(
        delete(Subscription).where(Subscription.tenant_id == b["tenant"].id)
    )
    owner_db.commit()
    snap = ent.resolve_entitlements(owner_db, tenant_id=b["tenant"].id)
    assert "missing_subscription" in snap["resolution_notes"]
    assert snap["enforcement_active"] is True

    _ensure_sub(owner_db, b["tenant"])
    plat_actor = b["admin"].id
    subs.assign_plan(
        owner_db,
        tenant_id=b["tenant"].id,
        actor_id=plat_actor,
        plan_code="growth-v1",
    )
    owner_db.commit()
    snap2 = ent.resolve_entitlements(owner_db, tenant_id=b["tenant"].id)
    assert snap2["features"]["inventory"] is True
    by_key = {e["key"]: e for e in snap2["evaluations"]}
    assert by_key["inventory"]["result"] == "allowed"


def test_get_entitlements_is_read_only(
    client, owner_db, make_owner_user, make_tenant
):
    from app.modules.subscriptions import service as subs

    b = provision_tenant(
        owner_db, make_owner_user, make_tenant, slug=f"er-{uuid.uuid4().hex[:6]}"
    )
    _ensure_sub(owner_db, b["tenant"])
    sub = subs.require_subscription(owner_db, tenant_id=b["tenant"].id)
    before = (sub.status, sub.updated_at, sub.plan_id)
    doc = login_client(client, email=b["admin"].email)
    assert (
        doc.get(
            f"/api/v1/tenants/{b['tenant'].id}/entitlements",
            headers=tenant_headers(str(b["tenant"].id)),
        ).status_code
        == 200
    )
    owner_db.refresh(sub)
    assert (sub.status, sub.updated_at, sub.plan_id) == before
