"""P2.3 commercial state gates, feature enforcement, portal separation."""

from __future__ import annotations

import uuid

import pytest

from app.platform.errors import EntitlementExceededError, ForbiddenError
from tests.helpers import login_client, provision_scheduling, provision_tenant, tenant_headers


def _set_status(owner_db, tenant, _admin, status: str) -> None:
    """Synthetic commercial status for policy tests (not a transition audit)."""
    from app.modules.subscriptions import service as subs

    sub = subs.require_subscription(owner_db, tenant_id=tenant.id)
    sub.status = status
    owner_db.commit()
    assert subs.require_subscription(owner_db, tenant_id=tenant.id).status == status


def test_past_due_blocks_capacity_allows_business(
    owner_db, make_owner_user, make_tenant
):
    from app.modules.clinics import service as clinics_service
    from app.modules.scheduling import service as scheduling_service
    from app.modules.subscriptions import commercial_policy as cpol

    b = provision_scheduling(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=f"pd-{uuid.uuid4().hex[:6]}",
    )
    _set_status(owner_db, b["tenant"], b["admin"], "past_due")

    # Capacity expand denied.
    with pytest.raises(EntitlementExceededError) as ei:
        clinics_service.create_location(
            owner_db, tenant=b["tenant"], name=f"X-{uuid.uuid4().hex[:4]}"
        )
    assert ei.value.reason_code in (
        "capacity_expand_not_allowed",
        "subscription_inactive",
    )
    owner_db.rollback()

    # Business create still allowed.
    d = cpol.evaluate_operation(
        owner_db,
        tenant_id=b["tenant"].id,
        category=cpol.OpCategory.BUSINESS_CREATE,
        operation="appointment.create",
    )
    assert d.allowed is True

    from datetime import datetime, timedelta

    from app.platform.time import UTC

    start = (datetime.now(UTC) + timedelta(days=3)).replace(
        hour=11, minute=0, second=0, microsecond=0
    )
    appt = scheduling_service.create_appointment(
        owner_db,
        tenant_id=b["tenant"].id,
        actor_id=b["admin"].id,
        patient_id=b["patient"].id,
        practitioner_id=b["practitioner"].id,
        location_id=b["location"].id,
        start=start,
        duration_minutes=30,
    )
    owner_db.commit()
    assert appt.id is not None

    # Recovery: deactivate location under past_due.
    clinics_service.set_location_active(
        owner_db,
        tenant_id=b["tenant"].id,
        location_id=b["location"].id,
        is_active=False,
    )
    owner_db.commit()


def test_expired_blocks_business_create(owner_db, make_owner_user, make_tenant):
    from app.modules.scheduling import service as scheduling_service
    from datetime import datetime, timedelta

    from app.platform.time import UTC

    b = provision_scheduling(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=f"ex-{uuid.uuid4().hex[:6]}",
    )
    _set_status(owner_db, b["tenant"], b["admin"], "expired")
    start = (datetime.now(UTC) + timedelta(days=3)).replace(
        hour=11, minute=0, second=0, microsecond=0
    )
    with pytest.raises(EntitlementExceededError) as ei:
        scheduling_service.create_appointment(
            owner_db,
            tenant_id=b["tenant"].id,
            actor_id=b["admin"].id,
            patient_id=b["patient"].id,
            practitioner_id=b["practitioner"].id,
            location_id=b["location"].id,
            start=start,
            duration_minutes=30,
        )
    assert ei.value.reason_code == "subscription_inactive"


def test_starter_blocks_inventory_feature(owner_db, make_owner_user, make_tenant):
    from app.modules.inventory import service as inv
    from app.modules.subscriptions import service as subs

    b = provision_tenant(
        owner_db, make_owner_user, make_tenant, slug=f"invf-{uuid.uuid4().hex[:6]}"
    )
    subs.assign_plan(
        owner_db,
        tenant_id=b["tenant"].id,
        actor_id=b["admin"].id,
        plan_code="starter-v1",
    )
    owner_db.commit()
    with pytest.raises(ForbiddenError):
        inv.create_item(
            owner_db,
            tenant_id=b["tenant"].id,
            sku=f"SKU-{uuid.uuid4().hex[:6]}",
            name="Blocked Item",
        )


def test_feature_does_not_grant_permission(
    client, owner_db, make_owner_user, make_tenant
):
    """Doctor with inventory feature on plan still needs inventory permission."""
    from app.modules.identity import service as identity_service
    from app.modules.tenancy import service as tenancy_service

    b = provision_tenant(
        owner_db, make_owner_user, make_tenant, slug=f"permf-{uuid.uuid4().hex[:6]}"
    )
    doc = identity_service.create_user(
        owner_db,
        email=f"docf-{uuid.uuid4().hex[:6]}@example.com",
        display_name="Doc",
        password="password-12345-abc",
    )
    tenancy_service.create_membership(
        owner_db,
        user=doc,
        tenant=b["tenant"],
        role=tenancy_service.get_seed_role(owner_db, "doctor"),
    )
    owner_db.commit()
    c = login_client(client, email=doc.email)
    r = c.post(
        f"/api/v1/tenants/{b['tenant'].id}/inventory/items",
        headers=tenant_headers(str(b["tenant"].id)),
        json={"sku": "X1", "name": "Item"},
    )
    assert r.status_code == 403


def test_portal_access_under_commercial_states(
    client, owner_db, make_owner_user, make_tenant
):
    """Portal reads succeed for past_due/grace/expired when tenant is active."""
    from app.modules.portal import service as portal_service
    from app.modules.tenancy import service as tenancy_service
    from app.modules.tenancy.models import TENANT_SUSPENDED

    b = provision_scheduling(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=f"porta-{uuid.uuid4().hex[:6]}",
    )
    email = f"portal-{uuid.uuid4().hex[:6]}@example.com"
    portal_service.enroll_patient_user(
        owner_db,
        tenant_id=b["tenant"].id,
        email=email,
        patient_id=b["patient"].id,
        actor_id=b["admin"].id,
        display_name="Portal Pat",
    )
    # Set a usable password for login.
    from app.modules.identity import service as identity_service

    user = identity_service.get_user_by_email(owner_db, email)
    assert user is not None
    identity_service.set_password(owner_db, user, "password-12345-abc")
    owner_db.commit()

    from app.modules.subscriptions import commercial_policy as cpol
    from app.platform.ratelimit import limiter

    pc = login_client(client, email=email)
    for status in ("past_due", "grace", "expired", "cancelled", "suspended"):
        _set_status(owner_db, b["tenant"], b["admin"], status)
        assert tenancy_service.get_tenant(owner_db, b["tenant"].id).status == "active"
        d = cpol.evaluate_operation(
            owner_db,
            tenant_id=b["tenant"].id,
            category=cpol.OpCategory.PATIENT_PORTAL_ACCESS,
            feature_key="patient_portal",
        )
        assert d.allowed is True, status
        limiter._hits.clear()
        r = pc.get("/api/v1/portal/me", headers=tenant_headers(str(b["tenant"].id)))
        assert r.status_code == 200, (status, r.text)

    # Abuse suspension still blocks portal (independent axis).
    from app.modules.subscriptions import service as subs

    sub = subs.require_subscription(owner_db, tenant_id=b["tenant"].id)
    sub.status = "active"
    tenancy_service.set_tenant_status(owner_db, b["tenant"], status=TENANT_SUSPENDED)
    owner_db.commit()
    limiter._hits.clear()
    r = pc.get("/api/v1/portal/me", headers=tenant_headers(str(b["tenant"].id)))
    assert r.status_code == 403


def test_portal_enroll_blocked_when_feature_off(
    owner_db, make_owner_user, make_tenant
):
    from app.modules.portal import service as portal_service
    from app.modules.subscriptions import service as subs
    from app.modules.subscriptions.models import SubscriptionPlan
    from sqlalchemy.orm.attributes import flag_modified

    b = provision_scheduling(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=f"penr-{uuid.uuid4().hex[:6]}",
    )
    sub = subs.require_subscription(owner_db, tenant_id=b["tenant"].id)
    plan = owner_db.get(SubscriptionPlan, sub.plan_id)
    assert plan is not None
    feats = dict(plan.features or {})
    feats["patient_portal"] = False
    plan.features = feats
    flag_modified(plan, "features")
    owner_db.commit()
    with pytest.raises(ForbiddenError):
        portal_service.enroll_patient_user(
            owner_db,
            tenant_id=b["tenant"].id,
            email=f"nope-{uuid.uuid4().hex[:6]}@example.com",
            patient_id=b["patient"].id,
            actor_id=b["admin"].id,
        )


def test_deactivate_location_when_expired(owner_db, make_owner_user, make_tenant):
    from app.modules.clinics import service as clinics_service

    b = provision_tenant(
        owner_db, make_owner_user, make_tenant, slug=f"rec-{uuid.uuid4().hex[:6]}"
    )
    _set_status(owner_db, b["tenant"], b["admin"], "expired")
    loc = clinics_service.set_location_active(
        owner_db,
        tenant_id=b["tenant"].id,
        location_id=b["location"].id,
        is_active=False,
    )
    owner_db.commit()
    assert loc.is_active is False


def test_policy_snapshot_on_entitlements(
    client, owner_db, make_owner_user, make_tenant
):
    b = provision_tenant(
        owner_db, make_owner_user, make_tenant, slug=f"snap-{uuid.uuid4().hex[:6]}"
    )
    doc = login_client(client, email=b["admin"].email)
    body = doc.get(
        f"/api/v1/tenants/{b['tenant'].id}/entitlements",
        headers=tenant_headers(str(b["tenant"].id)),
    ).json()
    assert body["commercial_policy"]["patient_portal_access_ignores_commercial"] is True
    assert "inventory" in body["enforced_keys"]
    assert body["commercial_policy"]["capacity_expand_allowed"] is True
