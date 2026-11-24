"""P2.0 commercial plan catalog + subscription foundation."""

from __future__ import annotations

import uuid

from tests.helpers import (
    login_client,
    make_platform_admin,
    provision_tenant,
    tenant_headers,
)


def _provision(owner_db, make_owner_user, make_tenant):
    return provision_tenant(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=f"sub-{uuid.uuid4().hex[:6]}",
        admin_email=f"sub-{uuid.uuid4().hex[:6]}@example.com",
    )


def test_list_plans_and_tenant_subscription(
    client, owner_db, make_owner_user, make_tenant
):
    b = _provision(owner_db, make_owner_user, make_tenant)
    # Workspace provision path: ensure trial subscription exists
    from app.modules.subscriptions import service as subs

    if subs.get_subscription(owner_db, tenant_id=b["tenant"].id) is None:
        subs.create_trial_subscription(owner_db, tenant=b["tenant"])
        owner_db.commit()

    doc = login_client(client, email=b["admin"].email)
    plans = doc.get("/api/v1/plans")
    assert plans.status_code == 200, plans.text
    codes = {p["code"] for p in plans.json()}
    assert "trial-14d" in codes
    assert "starter-v1" in codes
    for p in plans.json():
        assert p["limits"]["enforced"] is False
        assert p["currency"] == "INR"

    h = tenant_headers(str(b["tenant"].id))
    sub = doc.get(f"/api/v1/tenants/{b['tenant'].id}/subscription", headers=h)
    assert sub.status_code == 200, sub.text
    body = sub.json()
    assert body["tenant_id"] == str(b["tenant"].id)
    assert body["status"] == "trial"
    assert body["limits_enforced"] is True
    assert body["plan"]["code"] == "trial-14d"
    assert body["provider_ref"] is None

    events = doc.get(
        f"/api/v1/tenants/{b['tenant'].id}/subscription/events", headers=h
    )
    assert events.status_code == 200
    assert len(events.json()) >= 1


def test_cross_tenant_subscription_isolation(
    client, owner_db, make_owner_user, make_tenant
):
    from app.modules.subscriptions import service as subs

    a = _provision(owner_db, make_owner_user, make_tenant)
    b = _provision(owner_db, make_owner_user, make_tenant)
    for bundle in (a, b):
        if subs.get_subscription(owner_db, tenant_id=bundle["tenant"].id) is None:
            subs.create_trial_subscription(owner_db, tenant=bundle["tenant"])
    owner_db.commit()

    doc_a = login_client(client, email=a["admin"].email)
    ha = tenant_headers(str(a["tenant"].id))
    # A cannot read B with A's tenant selector
    r = doc_a.get(
        f"/api/v1/tenants/{b['tenant'].id}/subscription", headers=ha
    )
    assert r.status_code in (403, 404)


def test_patient_cannot_read_subscription_admin(
    client, owner_db, make_owner_user, make_tenant
):
    from app.modules.identity import service as identity_service
    from app.modules.subscriptions import service as subs
    from app.modules.tenancy import service as tenancy_service

    b = _provision(owner_db, make_owner_user, make_tenant)
    if subs.get_subscription(owner_db, tenant_id=b["tenant"].id) is None:
        subs.create_trial_subscription(owner_db, tenant=b["tenant"])
    patient_user = identity_service.create_user(
        owner_db,
        email=f"pat-{uuid.uuid4().hex[:6]}@example.com",
        display_name="Portal Pat",
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
    h = tenant_headers(str(b["tenant"].id))
    r = pat.get(f"/api/v1/tenants/{b['tenant'].id}/subscription", headers=h)
    assert r.status_code == 403


def test_staff_without_manage_cannot_assign_plan(
    client, owner_db, make_owner_user, make_tenant
):
    from app.modules.subscriptions import service as subs

    b = _provision(owner_db, make_owner_user, make_tenant)
    if subs.get_subscription(owner_db, tenant_id=b["tenant"].id) is None:
        subs.create_trial_subscription(owner_db, tenant=b["tenant"])
        owner_db.commit()

    doc = login_client(client, email=b["admin"].email)
    h = tenant_headers(str(b["tenant"].id))
    # Tenant admin is not platform admin — assign requires platform
    r = doc.post(
        f"/api/v1/tenants/{b['tenant'].id}/subscription/assign-plan",
        headers=h,
        json={"plan_code": "starter-v1"},
    )
    assert r.status_code == 403


def test_platform_assign_plan_and_invalid_transition(
    client, owner_db, make_owner_user, make_tenant
):
    from app.modules.subscriptions import service as subs
    from app.modules.tenancy import service as tenancy_service

    b = _provision(owner_db, make_owner_user, make_tenant)
    if subs.get_subscription(owner_db, tenant_id=b["tenant"].id) is None:
        subs.create_trial_subscription(owner_db, tenant=b["tenant"])
    plat_user = make_platform_admin(
        owner_db, make_owner_user, email=f"plat-{uuid.uuid4().hex[:6]}@example.com"
    )
    owner_db.commit()

    plat = login_client(client, email=plat_user.email)
    tid = b["tenant"].id
    status_before = tenancy_service.get_tenant(owner_db, tid).status

    assigned = plat.post(
        f"/api/v1/tenants/{tid}/subscription/assign-plan",
        json={"plan_code": "starter-v1", "note": "pilot upgrade"},
    )
    assert assigned.status_code == 200, assigned.text
    body = assigned.json()
    assert body["plan"]["code"] == "starter-v1"
    assert body["status"] == "active"
    assert body["limits_enforced"] is True

    bad = plat.post(
        f"/api/v1/tenants/{tid}/subscription/transition",
        json={"status": "trial"},
    )
    assert bad.status_code in (409, 422)

    ok = plat.post(
        f"/api/v1/tenants/{tid}/subscription/transition",
        json={"status": "past_due", "note": "manual past_due for test"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "past_due"

    assert tenancy_service.get_tenant(owner_db, tid).status == status_before

    doc = login_client(client, email=b["admin"].email)
    h = tenant_headers(str(tid))
    events = doc.get(f"/api/v1/tenants/{tid}/subscription/events", headers=h)
    assert events.status_code == 200
    types = {e["event_type"] for e in events.json()}
    assert "plan_assigned" in types
    assert "status_transition" in types


def test_duplicate_subscription_rejected(owner_db, make_owner_user, make_tenant):
    from app.modules.subscriptions import service as subs
    from app.platform.errors import ConflictError
    import pytest

    b = _provision(owner_db, make_owner_user, make_tenant)
    if subs.get_subscription(owner_db, tenant_id=b["tenant"].id) is None:
        subs.create_trial_subscription(owner_db, tenant=b["tenant"])
        owner_db.commit()
    with pytest.raises(ConflictError):
        subs.create_trial_subscription(owner_db, tenant=b["tenant"])


def test_plan_revision_preserves_prior_assignment(
    owner_db, make_owner_user, make_tenant
):
    from app.modules.subscriptions import service as subs

    b = _provision(owner_db, make_owner_user, make_tenant)
    if subs.get_subscription(owner_db, tenant_id=b["tenant"].id) is None:
        subs.create_trial_subscription(owner_db, tenant=b["tenant"])
    starter = subs.get_plan_by_code(owner_db, code="starter-v1")
    sub = subs.require_subscription(owner_db, tenant_id=b["tenant"].id)
    sub.plan_id = starter.id
    owner_db.flush()
    # New revision deactivates prior for catalog, assignment keeps old plan_id
    v2 = subs.create_plan_revision(
        owner_db,
        family_code="starter",
        name="Starter Plus",
        description="v2",
        max_locations=2,
        max_practitioners=8,
        max_staff_seats=20,
        price_minor=599900,
    )
    owner_db.commit()
    owner_db.refresh(starter)
    assert starter.is_active is False
    assert v2.version == 2
    owner_db.refresh(sub)
    assert sub.plan_id == starter.id
    detail = subs.subscription_detail(owner_db, subscription=sub)
    assert detail["plan"]["code"] == "starter-v1"
    assert detail["plan"]["version"] == 1
