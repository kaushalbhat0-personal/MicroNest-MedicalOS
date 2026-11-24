"""P2.2 atomic entitlement enforcement — real PostgreSQL concurrency."""

from __future__ import annotations

import threading
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.platform.errors import EntitlementExceededError
from app.platform.time import now as utcnow
from tests.helpers import login_client, provision_tenant, tenant_headers


def _assign_starter(owner_db, _client, tenant, admin_email: str) -> None:
    from app.modules.identity.models import User
    from app.modules.subscriptions import service as subs

    admin = owner_db.execute(select(User).where(User.email == admin_email)).scalar_one()
    if subs.get_subscription(owner_db, tenant_id=tenant.id) is None:
        subs.create_trial_subscription(owner_db, tenant=tenant)
    subs.assign_plan(
        owner_db,
        tenant_id=tenant.id,
        actor_id=admin.id,
        plan_code="starter-v1",
    )
    owner_db.commit()


def test_concurrent_staff_invites_single_winner(
    client, owner_db, make_owner_user, make_tenant, app_factory
):
    """Starter max_staff_seats=15; fill to 14 then race two invites → one seat left."""
    from app.modules.identity import service as identity_service
    from app.modules.subscriptions import service as subs
    from app.modules.tenancy import service as tenancy_service
    from app.modules.tenancy.models import Invitation

    b = provision_tenant(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=f"seat-race-{uuid.uuid4().hex[:6]}",
    )
    _assign_starter(owner_db, client, b["tenant"], b["admin"].email)
    # Starter: 15 seats. Owner already uses 1. Fill to 14 active seats.
    role = tenancy_service.get_seed_role(owner_db, "receptionist")
    for i in range(13):
        u = identity_service.create_user(
            owner_db,
            email=f"fill-{i}-{uuid.uuid4().hex[:6]}@example.com",
            display_name=f"Fill {i}",
            password="password-12345-abc",
        )
        tenancy_service.create_membership(
            owner_db, user=u, tenant=b["tenant"], role=role
        )
    owner_db.commit()
    plan = subs.require_subscription(owner_db, tenant_id=b["tenant"].id)
    from app.modules.subscriptions.models import SubscriptionPlan

    lim = owner_db.get(SubscriptionPlan, plan.plan_id).max_staff_seats
    from app.modules.subscriptions import enforcement as enf

    usage = enf.staff_seat_usage(owner_db, tenant_id=b["tenant"].id)["consumed"]
    assert usage == lim - 1, (usage, lim)

    tid = str(b["tenant"].id)
    gate = threading.Barrier(3)
    results: list[int] = []

    def attempt(n: int) -> None:
        c = TestClient(client.app, base_url="http://test")
        assert (
            c.post(
                "/api/v1/auth/login",
                json={"email": b["admin"].email, "password": "password-12345-abc"},
            ).status_code
            == 200
        )
        gate.wait(timeout=30)
        r = c.post(
            f"/api/v1/tenants/{tid}/invites",
            headers=tenant_headers(tid),
            json={
                "email": f"race-{n}-{uuid.uuid4().hex[:6]}@example.com",
                "role": "receptionist",
            },
        )
        results.append(r.status_code)

    threads = [threading.Thread(target=attempt, args=(i,)) for i in (1, 2)]
    for t in threads:
        t.start()
    gate.wait(timeout=30)
    for t in threads:
        t.join(timeout=120)

    assert sorted(results) == [200, 409], results
    pending = owner_db.execute(
        select(Invitation).where(
            Invitation.tenant_id == b["tenant"].id,
            Invitation.status == "pending",
        )
    ).scalars().all()
    # Exactly one new reservation from the race (fill created none).
    assert len(pending) == 1
    final = enf.staff_seat_usage(owner_db, tenant_id=b["tenant"].id)["consumed"]
    assert final == lim


def test_invitation_accept_does_not_double_count(
    client, owner_db, make_owner_user, make_tenant
):
    from app.modules.subscriptions import enforcement as enf
    from app.modules.tenancy import service as tenancy_service

    b = provision_tenant(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=f"accept-{uuid.uuid4().hex[:6]}",
    )
    role = tenancy_service.get_seed_role(owner_db, "receptionist")
    inv, raw = tenancy_service.create_invitation(
        owner_db,
        tenant=b["tenant"],
        email=f"newbie-{uuid.uuid4().hex[:6]}@example.com",
        role=role,
        invited_by=b["admin"],
    )
    owner_db.commit()
    before = enf.staff_seat_usage(owner_db, tenant_id=b["tenant"].id)
    assert before["pending_reservations"] >= 1
    tenancy_service.accept_invitation(
        owner_db,
        token=raw,
        display_name="Newbie",
        password="password-12345-abc",
    )
    owner_db.commit()
    after = enf.staff_seat_usage(owner_db, tenant_id=b["tenant"].id)
    assert after["consumed"] == before["consumed"]
    assert after["pending_reservations"] == before["pending_reservations"] - 1
    assert after["active_memberships"] == before["active_memberships"] + 1


def test_revoke_and_expiry_release_reservation(
    owner_db, make_owner_user, make_tenant
):
    from app.modules.staff import service as staff_service
    from app.modules.subscriptions import enforcement as enf
    from app.modules.tenancy import service as tenancy_service
    from app.modules.tenancy.models import Invitation

    b = provision_tenant(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=f"rel-{uuid.uuid4().hex[:6]}",
    )
    role = tenancy_service.get_seed_role(owner_db, "receptionist")
    inv, _raw = tenancy_service.create_invitation(
        owner_db,
        tenant=b["tenant"],
        email=f"rel-{uuid.uuid4().hex[:6]}@example.com",
        role=role,
        invited_by=b["admin"],
    )
    owner_db.commit()
    mid = enf.staff_seat_usage(owner_db, tenant_id=b["tenant"].id)["consumed"]
    staff_service.revoke_invitation(
        owner_db, tenant_id=b["tenant"].id, invitation_id=inv.id
    )
    owner_db.commit()
    assert enf.staff_seat_usage(owner_db, tenant_id=b["tenant"].id)["consumed"] == mid - 1

    inv2, _ = tenancy_service.create_invitation(
        owner_db,
        tenant=b["tenant"],
        email=f"exp-{uuid.uuid4().hex[:6]}@example.com",
        role=role,
        invited_by=b["admin"],
        ttl_days=7,
    )
    owner_db.commit()
    mid2 = enf.staff_seat_usage(owner_db, tenant_id=b["tenant"].id)["consumed"]
    row = owner_db.get(Invitation, inv2.id)
    assert row is not None
    row.expires_at = utcnow() - timedelta(seconds=5)
    owner_db.commit()
    assert enf.staff_seat_usage(owner_db, tenant_id=b["tenant"].id)["consumed"] == mid2 - 1


def test_concurrent_location_create_single_winner(
    client, owner_db, make_owner_user, make_tenant
):
    b = provision_tenant(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=f"loc-race-{uuid.uuid4().hex[:6]}",
    )
    _assign_starter(owner_db, client, b["tenant"], b["admin"].email)
    # Starter max_locations=1; Main Clinic already exists → both creates must fail? 
    # One seat left would need 0 locations. So race with limit 1 and 0 active is needed.
    # Deactivate the main clinic first so exactly one reactivation/create slot exists.
    from app.modules.clinics import service as clinics_service

    clinics_service.set_location_active(
        owner_db,
        tenant_id=b["tenant"].id,
        location_id=b["location"].id,
        is_active=False,
        enforce_capacity=False,
    )
    owner_db.commit()

    tid = str(b["tenant"].id)
    gate = threading.Barrier(3)
    results: list[int] = []

    def attempt(n: int) -> None:
        c = TestClient(client.app, base_url="http://test")
        assert (
            c.post(
                "/api/v1/auth/login",
                json={"email": b["admin"].email, "password": "password-12345-abc"},
            ).status_code
            == 200
        )
        gate.wait(timeout=30)
        r = c.post(
            f"/api/v1/tenants/{tid}/locations",
            headers=tenant_headers(tid),
            json={"name": f"Branch {n}-{uuid.uuid4().hex[:4]}", "timezone": "Asia/Kolkata"},
        )
        results.append(r.status_code)

    threads = [threading.Thread(target=attempt, args=(i,)) for i in (1, 2)]
    for t in threads:
        t.start()
    gate.wait(timeout=30)
    for t in threads:
        t.join(timeout=120)
    assert sorted(results) == [200, 409], results
    from app.modules.subscriptions import entitlements as ent

    assert ent.count_active_locations(owner_db, tenant_id=b["tenant"].id) == 1


def test_concurrent_location_reactivation(
    client, owner_db, make_owner_user, make_tenant
):
    from app.modules.clinics import service as clinics_service

    b = provision_tenant(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=f"loc-re-{uuid.uuid4().hex[:6]}",
    )
    # Under trial (max 3): create second location, deactivate both, assign
    # starter (max 1), then race two reactivations → exactly one wins.
    loc2 = clinics_service.create_location(
        owner_db, tenant=b["tenant"], name=f"B-{uuid.uuid4().hex[:4]}"
    )
    clinics_service.set_location_active(
        owner_db, tenant_id=b["tenant"].id, location_id=b["location"].id, is_active=False
    )
    clinics_service.set_location_active(
        owner_db, tenant_id=b["tenant"].id, location_id=loc2.id, is_active=False
    )
    owner_db.commit()
    _assign_starter(owner_db, client, b["tenant"], b["admin"].email)

    tid = str(b["tenant"].id)
    gate = threading.Barrier(3)
    results: list[int] = []
    ids = [str(b["location"].id), str(loc2.id)]

    def attempt(loc_id: str) -> None:
        c = TestClient(client.app, base_url="http://test")
        assert (
            c.post(
                "/api/v1/auth/login",
                json={"email": b["admin"].email, "password": "password-12345-abc"},
            ).status_code
            == 200
        )
        gate.wait(timeout=30)
        r = c.patch(
            f"/api/v1/tenants/{tid}/locations/{loc_id}",
            headers=tenant_headers(tid),
            json={"is_active": True},
        )
        results.append(r.status_code)

    threads = [threading.Thread(target=attempt, args=(i,)) for i in ids]
    for t in threads:
        t.start()
    gate.wait(timeout=30)
    for t in threads:
        t.join(timeout=120)
    assert sorted(results) == [200, 409], results
    from app.modules.subscriptions import entitlements as ent

    assert ent.count_active_locations(owner_db, tenant_id=b["tenant"].id) == 1


def test_concurrent_practitioner_approval(
    client, owner_db, make_owner_user, make_tenant
):
    from app.modules.subscriptions import entitlements as ent
    from app.modules.subscriptions import service as subs
    from app.modules.subscriptions.models import SubscriptionPlan
    from app.modules.tenancy import service as tenancy_service

    b = provision_tenant(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=f"prac-{uuid.uuid4().hex[:6]}",
    )
    _assign_starter(owner_db, client, b["tenant"], b["admin"].email)
    sub = subs.require_subscription(owner_db, tenant_id=b["tenant"].id)
    lim = owner_db.get(SubscriptionPlan, sub.plan_id).max_practitioners  # 5
    # Fill to lim-1 approved practitioners.
    pending_ids: list[str] = []
    for i in range(lim - 1):
        p = tenancy_service.register_practitioner(
            owner_db, display_name=f"Dr Fill {i}"
        )
        tenancy_service.set_verification(
            owner_db, tenant=b["tenant"], practitioner=p, status="approved"
        )
    # Two pending candidates for the last slot.
    for i in range(2):
        p = tenancy_service.register_practitioner(
            owner_db, display_name=f"Dr Race {i}"
        )
        tenancy_service.set_verification(
            owner_db, tenant=b["tenant"], practitioner=p, status="pending"
        )
        pending_ids.append(str(p.id))
    owner_db.commit()
    assert ent.count_approved_practitioners(owner_db, tenant_id=b["tenant"].id) == lim - 1

    tid = str(b["tenant"].id)
    gate = threading.Barrier(3)
    results: list[int] = []

    def attempt(prac_id: str) -> None:
        c = TestClient(client.app, base_url="http://test")
        assert (
            c.post(
                "/api/v1/auth/login",
                json={"email": b["admin"].email, "password": "password-12345-abc"},
            ).status_code
            == 200
        )
        gate.wait(timeout=30)
        r = c.post(
            f"/api/v1/tenants/{tid}/verification",
            headers=tenant_headers(tid),
            json={"practitioner_id": prac_id, "status": "approved"},
        )
        results.append(r.status_code)

    threads = [threading.Thread(target=attempt, args=(pid,)) for pid in pending_ids]
    for t in threads:
        t.start()
    gate.wait(timeout=30)
    for t in threads:
        t.join(timeout=120)
    assert sorted(results) == [200, 409], results
    assert ent.count_approved_practitioners(owner_db, tenant_id=b["tenant"].id) == lim


def test_patient_membership_does_not_consume_seat(
    owner_db, make_owner_user, make_tenant
):
    from app.modules.identity import service as identity_service
    from app.modules.subscriptions import enforcement as enf
    from app.modules.tenancy import service as tenancy_service

    b = provision_tenant(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=f"patseat-{uuid.uuid4().hex[:6]}",
    )
    before = enf.staff_seat_usage(owner_db, tenant_id=b["tenant"].id)["consumed"]
    patient_role = tenancy_service.get_seed_role(owner_db, "patient")
    u = identity_service.create_user(
        owner_db,
        email=f"patient-{uuid.uuid4().hex[:6]}@example.com",
        display_name="Pat",
        password="password-12345-abc",
    )
    tenancy_service.create_membership(
        owner_db, user=u, tenant=b["tenant"], role=patient_role
    )
    owner_db.commit()
    assert enf.staff_seat_usage(owner_db, tenant_id=b["tenant"].id)["consumed"] == before


def test_suspended_blocks_expanding_writes(
    owner_db, make_owner_user, make_tenant
):
    from app.modules.clinics import service as clinics_service
    from app.modules.subscriptions import service as subs

    b = provision_tenant(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=f"sus-{uuid.uuid4().hex[:6]}",
    )
    subs.transition_status(
        owner_db,
        tenant_id=b["tenant"].id,
        actor_id=b["admin"].id,
        new_status="suspended",
        note="p22",
    )
    owner_db.commit()
    with pytest.raises(EntitlementExceededError) as ei:
        clinics_service.create_location(
            owner_db, tenant=b["tenant"], name=f"X-{uuid.uuid4().hex[:4]}"
        )
    assert ei.value.reason_code == "subscription_inactive"
    # Deactivation still allowed (reducing).
    clinics_service.set_location_active(
        owner_db,
        tenant_id=b["tenant"].id,
        location_id=b["location"].id,
        is_active=False,
    )
    owner_db.commit()


def test_cross_tenant_capacity_isolated(
    owner_db, make_owner_user, make_tenant
):
    from app.modules.clinics import service as clinics_service
    from app.modules.subscriptions import entitlements as ent

    a = provision_tenant(
        owner_db, make_owner_user, make_tenant, slug=f"iso-a-{uuid.uuid4().hex[:6]}"
    )
    b = provision_tenant(
        owner_db, make_owner_user, make_tenant, slug=f"iso-b-{uuid.uuid4().hex[:6]}"
    )
    _assign_starter(owner_db, None, a["tenant"], a["admin"].email)
    # Tenant A at location capacity; B can still create under trial (max 3).
    with pytest.raises(EntitlementExceededError):
        clinics_service.create_location(
            owner_db, tenant=a["tenant"], name=f"A2-{uuid.uuid4().hex[:4]}"
        )
    owner_db.rollback()
    loc = clinics_service.create_location(
        owner_db, tenant=b["tenant"], name=f"B2-{uuid.uuid4().hex[:4]}"
    )
    owner_db.commit()
    assert loc.tenant_id == b["tenant"].id
    assert ent.count_active_locations(owner_db, tenant_id=a["tenant"].id) == 1
    assert ent.count_active_locations(owner_db, tenant_id=b["tenant"].id) >= 2


def test_permission_denial_independent_of_capacity(
    client, owner_db, make_owner_user, make_tenant
):
    """User without locations.manage is 403 even when capacity remains."""
    from app.modules.identity import service as identity_service
    from app.modules.tenancy import service as tenancy_service

    b = provision_tenant(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=f"perm-{uuid.uuid4().hex[:6]}",
    )
    doc = identity_service.create_user(
        owner_db,
        email=f"doc-{uuid.uuid4().hex[:6]}@example.com",
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
        f"/api/v1/tenants/{b['tenant'].id}/locations",
        headers=tenant_headers(str(b["tenant"].id)),
        json={"name": "Unauthorized Branch"},
    )
    assert r.status_code == 403


def test_failed_txn_releases_lock_no_leak(
    owner_db, make_owner_user, make_tenant, app_factory
):
    """Rollback after lock must not leave a reservation."""
    from app.modules.subscriptions import enforcement as enf
    from app.modules.tenancy import service as tenancy_service
    from app.modules.tenancy.models import Invitation

    b = provision_tenant(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=f"leak-{uuid.uuid4().hex[:6]}",
    )
    before = enf.staff_seat_usage(owner_db, tenant_id=b["tenant"].id)["consumed"]
    role = tenancy_service.get_seed_role(owner_db, "receptionist")
    try:
        tenancy_service.create_invitation(
            owner_db,
            tenant=b["tenant"],
            email=f"leak-{uuid.uuid4().hex[:6]}@example.com",
            role=role,
            invited_by=b["admin"],
        )
        owner_db.flush()
        raise RuntimeError("force rollback")
    except RuntimeError:
        owner_db.rollback()
    after = enf.staff_seat_usage(owner_db, tenant_id=b["tenant"].id)["consumed"]
    assert after == before
    assert (
        owner_db.execute(
            select(Invitation).where(Invitation.tenant_id == b["tenant"].id)
        ).scalars().all()
        == []
    )
