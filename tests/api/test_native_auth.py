"""Native JSON auth (desktop) — additive to cookie auth; PostgreSQL-backed."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.modules.tenancy import service as tenancy_service
from tests.helpers import login_client, provision_tenant, tenant_headers


def _native_login(
    client: TestClient,
    *,
    email: str,
    password: str = "password-12345-abc",
    device_label: str = "PoC-Workstation",
) -> tuple[TestClient, dict]:
    fresh = TestClient(client.app, base_url="http://test")
    r = fresh.post(
        "/api/v1/auth/native/login",
        json={
            "email": email,
            "password": password,
            "client_platform": "windows",
            "device_label": device_label,
            "client_instance_id": str(uuid.uuid4()),
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    assert "." in body["refresh_token"]
    # Must not set browser auth cookies for native login.
    assert r.cookies.get("hos_access") is None
    assert r.cookies.get("hos_refresh") is None
    return fresh, body


def test_native_login_me_and_workspace(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    ctx = provision_tenant(
        owner_db, make_owner_user, make_tenant, admin_email="native-admin@example.com"
    )
    _, body = _native_login(client, email="native-admin@example.com")
    assert body["email"] == "native-admin@example.com"
    assert any(t["id"] == str(ctx["tenant"].id) for t in body["tenants"])

    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert me.status_code == 200, me.text

    wc = client.get(
        f"/api/v1/tenants/{ctx['tenant'].id}/workspace-context",
        headers={
            "Authorization": f"Bearer {body['access_token']}",
            **tenant_headers(ctx["tenant"].id),
        },
    )
    assert wc.status_code == 200, wc.text
    assert isinstance(wc.json()["permissions"], list)
    assert len(wc.json()["permissions"]) > 0
    assert wc.json()["role"]


def test_native_invalid_password(client, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    make_owner_user(email="native-badpw@example.com")
    r = client.post(
        "/api/v1/auth/native/login",
        json={
            "email": "native-badpw@example.com",
            "password": "wrong-password-xyz",
            "client_platform": "windows",
        },
    )
    assert r.status_code == 401


def test_native_disabled_account(client, owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    user = make_owner_user(email="native-disabled@example.com")
    user.is_active = False
    owner_db.commit()
    r = client.post(
        "/api/v1/auth/native/login",
        json={
            "email": "native-disabled@example.com",
            "password": "password-12345-abc",
            "client_platform": "windows",
        },
    )
    assert r.status_code == 401


def test_native_unauthorized_tenant(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    ctx = provision_tenant(
        owner_db, make_owner_user, make_tenant, admin_email="native-a@example.com"
    )
    other = make_tenant(slug=f"other-{uuid.uuid4().hex[:6]}")
    _, body = _native_login(client, email="native-a@example.com")
    r = client.get(
        f"/api/v1/tenants/{other.id}",
        headers={
            "Authorization": f"Bearer {body['access_token']}",
            **tenant_headers(other.id),
        },
    )
    assert r.status_code in (403, 404)
    # Valid tenant still works
    ok = client.get(
        f"/api/v1/tenants/{ctx['tenant'].id}",
        headers={
            "Authorization": f"Bearer {body['access_token']}",
            **tenant_headers(ctx["tenant"].id),
        },
    )
    assert ok.status_code == 200, ok.text


def test_native_multiple_workspaces(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    user = make_owner_user(email="native-multi@example.com")
    t1 = make_tenant(slug=f"m1-{uuid.uuid4().hex[:6]}")
    t2 = make_tenant(slug=f"m2-{uuid.uuid4().hex[:6]}")
    role = tenancy_service.get_seed_role(owner_db, "tenant_admin")
    tenancy_service.create_membership(
        owner_db, user=user, tenant=t1, role=role, is_primary=True
    )
    tenancy_service.create_membership(
        owner_db, user=user, tenant=t2, role=role, is_primary=False
    )
    owner_db.commit()
    _, body = _native_login(client, email="native-multi@example.com")
    ids = {t["id"] for t in body["tenants"]}
    assert str(t1.id) in ids and str(t2.id) in ids


def test_native_refresh_rotation_and_reuse(
    client, make_owner_user
) -> None:  # type: ignore[no-untyped-def]
    make_owner_user(email="native-refresh@example.com")
    _, body = _native_login(client, email="native-refresh@example.com")
    old = body["refresh_token"]
    r1 = client.post("/api/v1/auth/native/refresh", json={"refresh_token": old})
    assert r1.status_code == 200, r1.text
    new = r1.json()["refresh_token"]
    assert new != old
    # Old rejected; family killed on reuse
    assert client.post("/api/v1/auth/native/refresh", json={"refresh_token": old}).status_code == 401
    assert client.post("/api/v1/auth/native/refresh", json={"refresh_token": new}).status_code == 401


def test_native_logout_revokes_access(
    client, make_owner_user
) -> None:  # type: ignore[no-untyped-def]
    make_owner_user(email="native-logout@example.com")
    _, body = _native_login(client, email="native-logout@example.com")
    access = body["access_token"]
    out = client.post(
        "/api/v1/auth/native/logout",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert out.status_code == 204
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"}).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/native/refresh", json={"refresh_token": body["refresh_token"]}
        ).status_code
        == 401
    )


def test_browser_cookie_login_regression(
    client, make_owner_user
) -> None:  # type: ignore[no-untyped-def]
    make_owner_user(email="browser-reg@example.com")
    c = login_client(client, email="browser-reg@example.com")
    assert "hos_access" in c.cookies and "hos_refresh" in c.cookies
    assert c.get("/api/v1/auth/me").status_code == 200
    # Body must not include access_token (browser contract)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "browser-reg@example.com", "password": "password-12345-abc"},
    )
    assert login.status_code == 200
    assert "access_token" not in login.json()


def test_browser_refresh_and_logout_regression(
    client, make_owner_user
) -> None:  # type: ignore[no-untyped-def]
    make_owner_user(email="browser-ref@example.com")
    c = login_client(client, email="browser-ref@example.com")
    old = c.cookies.get("hos_refresh")
    fresh = TestClient(client.app, base_url="http://test")
    r = fresh.post("/api/v1/auth/refresh", headers={"Cookie": f"hos_refresh={old}"})
    assert r.status_code == 200, r.text
    assert r.cookies.get("hos_refresh")
    c2 = login_client(client, email="browser-ref@example.com")
    assert c2.post("/api/v1/auth/logout").status_code == 204
    assert c2.get("/api/v1/auth/me").status_code == 401


def test_revoked_membership_cannot_use_tenant(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    ctx = provision_tenant(
        owner_db, make_owner_user, make_tenant, admin_email="native-revmem@example.com"
    )
    _, body = _native_login(client, email="native-revmem@example.com")
    # Deactivate membership (server-derived authz must fail)
    from sqlalchemy import select

    from app.modules.tenancy.models import Membership

    m = owner_db.execute(
        select(Membership).where(
            Membership.user_id == ctx["admin"].id, Membership.tenant_id == ctx["tenant"].id
        )
    ).scalar_one()
    m.is_active = False
    owner_db.commit()
    r = client.get(
        f"/api/v1/tenants/{ctx['tenant'].id}",
        headers={
            "Authorization": f"Bearer {body['access_token']}",
            **tenant_headers(ctx["tenant"].id),
        },
    )
    assert r.status_code in (403, 404)
