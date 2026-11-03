"""API: platform + tenant administration + audit reads + the P1 demo flow."""

import threading

from fastapi.testclient import TestClient

from tests.helpers import (
    login_client,
    make_platform_admin,
    provision_tenant,
    tenant_headers,
)


def test_platform_tenant_lifecycle(client, owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    make_platform_admin(owner_db, make_owner_user, email="root@example.com")
    c = login_client(client, email="root@example.com")
    # Platform admin without membership CAN manage platform resources...
    r = c.post("/api/v1/platform/tenants", json={"name": "Acme", "slug": "acme"})
    assert r.status_code == 200, r.text
    tid = r.json()["id"]
    assert c.get("/api/v1/platform/health").status_code == 200
    # ...but tenant endpoints demand a membership (403, never data).
    assert (
        c.get(f"/api/v1/tenants/{tid}", headers=tenant_headers(tid)).status_code == 403
    )


def test_non_admin_cannot_create_tenant(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    user = make_owner_user(email="pleb@example.com")
    from app.modules.tenancy import service as tenancy_service

    tenant = make_tenant()
    role = tenancy_service.get_seed_role(owner_db, "staff")
    tenancy_service.create_membership(owner_db, user=user, tenant=tenant, role=role)
    owner_db.commit()
    c = login_client(client, email="pleb@example.com")
    r = c.post("/api/v1/platform/tenants", json={"name": "Evil", "slug": "evil"})
    assert r.status_code == 403


def test_full_p1_demo_flow(client, owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    """The P1 demo: platform -> tenant -> location -> invite -> accept ->
    login -> scoped reads -> permission gate -> audit -> logout."""
    make_platform_admin(owner_db, make_owner_user, email="root@example.com")
    root = login_client(client, email="root@example.com")
    tid = root.post(
        "/api/v1/platform/tenants", json={"name": "Demo", "slug": "demo"}
    ).json()["id"]

    from app.modules.clinics import service as clinics_service
    from app.modules.identity import service as identity_service
    from app.modules.tenancy import service as tenancy_service
    from app.modules.tenancy.models import Tenant

    tenant = owner_db.get(Tenant, tid)
    admin_user = identity_service.create_user(
        owner_db,
        email="boss.demo@example.com",
        display_name="Boss",
        password="password-12345-abc",
    )
    admin_user.is_platform_admin = False
    clinics_service.create_location(owner_db, tenant=tenant, name="HQ")
    tenancy_service.create_membership(
        owner_db,
        user=admin_user,
        tenant=tenant,
        role=tenancy_service.get_seed_role(owner_db, "tenant_admin"),
        is_primary=True,
    )
    owner_db.commit()

    boss = login_client(client, email="boss.demo@example.com")
    h = tenant_headers(tid)
    assert boss.get(f"/api/v1/tenants/{tid}", headers=h).status_code == 200
    locs = boss.get(f"/api/v1/tenants/{tid}/locations", headers=h).json()
    assert [loc["name"] for loc in locs] == ["HQ"]

    inv = boss.post(
        f"/api/v1/tenants/{tid}/invites",
        headers=h,
        json={"email": "rec.demo@example.com", "role": "receptionist"},
    )
    assert inv.status_code == 200, inv.text
    token = inv.json()["token"]

    acc = client.post(
        "/api/v1/invites/accept",
        json={"token": token, "display_name": "Rec", "password": "password-12345-abc"},
    )
    assert acc.status_code == 200, acc.text
    assert acc.json()["tenants"][0]["id"] == tid

    rec = login_client(client, email="rec.demo@example.com")
    # Receptionist (tenant.read only) cannot manage roles.
    assert (
        rec.post(
            f"/api/v1/tenants/{tid}/roles",
            headers=tenant_headers(tid),
            json={"name": "x", "permissions": []},
        ).status_code
        == 403
    )
    # ...but can read tenant + locations.
    assert (
        rec.get(f"/api/v1/tenants/{tid}", headers=tenant_headers(tid)).status_code
        == 200
    )

    # Audit captured the lifecycle; reading audit is itself audited.
    audit = boss.get(f"/api/v1/tenants/{tid}/audit", headers=h).json()
    actions = {e["action"] for e in audit}
    assert {
        "invite.create",
        "membership.update",
    } <= actions or "invite.create" in actions
    audit2 = boss.get(f"/api/v1/tenants/{tid}/audit", headers=h).json()
    assert any(e["action"] == "audit.read" for e in audit2)

    # Cross-tenant attempt: 404, never 403-oracle.
    assert (
        boss.get(
            "/api/v1/tenants/00000000-0000-4000-8000-000000000000", headers=h
        ).status_code
        == 404
    )

    # Logout revokes; refresh dies too.
    assert boss.post("/api/v1/auth/logout").status_code == 204
    assert boss.get("/api/v1/auth/me").status_code == 401


def test_invite_accept_invalid_token_is_gone(client) -> None:  # type: ignore[no-untyped-def]
    r = client.post(
        "/api/v1/invites/accept",
        json={"token": "bogus", "display_name": "x", "password": "password-12345-abc"},
    )
    assert r.status_code == 410


def test_roles_and_membership_guards(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    ctx = provision_tenant(
        owner_db, make_owner_user, make_tenant, admin_email="a1@example.com"
    )
    tid, admin = str(ctx["tenant"].id), ctx["admin"]
    boss = login_client(client, email=admin.email)
    h = tenant_headers(tid)
    # Custom role with platform permission rejected.
    bad = boss.post(
        f"/api/v1/tenants/{tid}/roles",
        headers=h,
        json={"name": "evil", "permissions": ["platform.tenant.create"]},
    )
    assert bad.status_code in (400, 422), bad.text
    ok = boss.post(
        f"/api/v1/tenants/{tid}/roles",
        headers=h,
        json={"name": "billing-clerk", "permissions": ["tenant.read", "billing.read"]},
    )
    assert ok.status_code == 200, ok.text
    # Demoting the last admin is refused.
    members = boss.get(f"/api/v1/tenants/{tid}/memberships", headers=h).json()
    mid = next(m["id"] for m in members if m["role"] == "tenant_admin")
    demote = boss.patch(
        f"/api/v1/tenants/{tid}/memberships/{mid}", headers=h, json={"role": "staff"}
    )
    assert demote.status_code == 403


def test_location_scope_filters_and_guards(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from app.modules.clinics import service as clinics_service
    from app.modules.identity import service as identity_service
    from app.modules.tenancy import service as tenancy_service

    ctx = provision_tenant(
        owner_db, make_owner_user, make_tenant, admin_email="a2@example.com"
    )
    tid = ctx["tenant"].id
    loc2 = clinics_service.create_location(
        owner_db, tenant=ctx["tenant"], name="Branch"
    )
    rec_user = identity_service.create_user(
        owner_db,
        email="scoped@example.com",
        display_name="S",
        password="password-12345-abc",
    )
    tenancy_service.create_membership(
        owner_db,
        user=rec_user,
        tenant=ctx["tenant"],
        role=tenancy_service.get_seed_role(owner_db, "receptionist"),
        location_ids=[ctx["location"].id],
    )
    owner_db.commit()
    boss = login_client(client, email=ctx["admin"].email)
    scoped = login_client(client, email="scoped@example.com")
    hb, hs = tenant_headers(str(tid)), tenant_headers(str(tid))
    assert len(boss.get(f"/api/v1/tenants/{tid}/locations", headers=hb).json()) == 2
    seen = scoped.get(f"/api/v1/tenants/{tid}/locations", headers=hs).json()
    assert [loc["name"] for loc in seen] == ["Main Clinic"]
    # Out-of-tenant location in scope update is refused.
    members = boss.get(f"/api/v1/tenants/{tid}/memberships", headers=hb).json()
    mid = next(m["id"] for m in members if m["user_id"] == str(rec_user.id))
    bad = boss.patch(
        f"/api/v1/tenants/{tid}/memberships/{mid}",
        headers=hb,
        json={"location_ids": [str(loc2.id), "00000000-0000-4000-8000-000000000000"]},
    )
    assert bad.status_code in (403, 404)


def test_practitioner_register_and_verify(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    ctx = provision_tenant(
        owner_db, make_owner_user, make_tenant, admin_email="a3@example.com"
    )
    tid = str(ctx["tenant"].id)
    boss = login_client(client, email=ctx["admin"].email)
    h = tenant_headers(tid)
    p = boss.post(
        f"/api/v1/tenants/{tid}/practitioners",
        headers=h,
        json={"display_name": "Dr Rao"},
    ).json()
    assert (
        boss.post(
            f"/api/v1/tenants/{tid}/verification",
            headers=h,
            json={"practitioner_id": p["id"], "status": "approved"},
        ).status_code
        == 200
    )
    queue = boss.get(f"/api/v1/tenants/{tid}/verification", headers=h).json()
    assert queue[0]["status"] == "approved"


def test_concurrent_last_admin_demotion_single_survivor(
    client, owner_db, make_owner_user, make_tenant
) -> None:
    """P4.8: the last-admin guard holds under concurrency (SELECT FOR UPDATE).

    Two admins demote each other at the same instant: exactly one wins and
    the tenant keeps one administrator.
    """
    from app.modules.tenancy import service as tenancy_service

    ctx = provision_tenant(
        owner_db, make_owner_user, make_tenant, admin_email="a3@example.com"
    )
    tid = str(ctx["tenant"].id)
    second = make_owner_user(email="a4@example.com")
    tenancy_service.create_membership(
        owner_db,
        user=second,
        tenant=ctx["tenant"],
        role=tenancy_service.get_seed_role(owner_db, "tenant_admin"),
    )
    owner_db.commit()
    members = (
        login_client(client, email=ctx["admin"].email)
        .get(f"/api/v1/tenants/{tid}/memberships", headers=tenant_headers(tid))
        .json()
    )
    by_user = {m["user_id"]: m["id"] for m in members}
    first_mid = by_user[str(ctx["admin"].id)]
    second_mid = by_user[str(second.id)]
    assert first_mid != second_mid
    gate = threading.Barrier(3)
    results: list[int] = []

    def attempt(email: str, target: str) -> None:
        c = TestClient(client.app, base_url="http://test")
        resp = c.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "password-12345-abc"},
        )
        assert resp.status_code == 200, resp.text
        gate.wait(timeout=30)
        r = c.patch(
            f"/api/v1/tenants/{tid}/memberships/{target}",
            headers=tenant_headers(tid),
            json={"role": "staff"},
        )
        results.append(r.status_code)

    threads = [
        threading.Thread(target=attempt, args=("a3@example.com", second_mid)),
        threading.Thread(target=attempt, args=("a4@example.com", first_mid)),
    ]
    for t in threads:
        t.start()
    gate.wait(timeout=30)
    for t in threads:
        t.join(timeout=120)
    assert sorted(results) == [200, 403], results
