"""API: auth lifecycle — login/me/refresh/logout/reset, envelopes, oracles."""

from fastapi.testclient import TestClient

from app.modules.identity import service as identity_service
from tests.helpers import login_client


def test_login_me_logout(client, owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    make_owner_user(email="amy@example.com")
    c = login_client(client, email="amy@example.com")
    me = c.get("/api/v1/auth/me")
    assert me.status_code == 200, me.text
    assert me.json()["email"] == "amy@example.com"
    assert me.json()["tenants"] == []
    # No localStorage involved: tokens must be HttpOnly cookies.
    assert "hos_access" in c.cookies and "hos_refresh" in c.cookies
    out = c.post("/api/v1/auth/logout")
    assert out.status_code == 204
    assert c.get("/api/v1/auth/me").status_code == 401


def test_refresh_rotation_and_reuse_kills_family(
    client, owner_db, make_owner_user
) -> None:  # type: ignore[no-untyped-def]
    from fastapi.testclient import TestClient as TC

    make_owner_user(email="bob@example.com")
    c = login_client(client, email="bob@example.com")
    old_refresh = c.cookies.get("hos_refresh")
    assert old_refresh

    def attempt(refresh_value: str | None):  # type: ignore[no-untyped-def]
        # Cookie header directly: deterministic, no jar path/domain quirks.
        fresh = TC(client.app, base_url="http://test")
        headers = {"Cookie": f"hos_refresh={refresh_value}"} if refresh_value else {}
        return fresh.post("/api/v1/auth/refresh", headers=headers)

    r1 = attempt(old_refresh)
    assert r1.status_code == 200, r1.text
    new_refresh = r1.cookies.get("hos_refresh")
    assert new_refresh and new_refresh != old_refresh
    # Replaying the old refresh secret must fail closed (family revoked).
    assert attempt(old_refresh).status_code == 401
    # Even the "new" secret is now dead: whole family revoked.
    assert attempt(new_refresh).status_code == 401


def test_login_rejects_bad_credentials_without_oracle(
    client, owner_db, make_owner_user
) -> None:  # type: ignore[no-untyped-def]
    make_owner_user(email="carl@example.com")
    bad_pw = client.post(
        "/api/v1/auth/login",
        json={"email": "carl@example.com", "password": "wrong-password-xyz"},
    )
    no_user = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "wrong-password-xyz"},
    )
    assert bad_pw.status_code == 401 and no_user.status_code == 401
    assert bad_pw.json()["type"] == no_user.json()["type"]
    assert "trace_id" in bad_pw.json()


def test_password_reset_flow(client, owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    user = make_owner_user(email="dana@example.com")
    c1 = client.post(
        "/api/v1/auth/password-reset/request", json={"email": "dana@example.com"}
    )
    c2 = client.post(
        "/api/v1/auth/password-reset/request", json={"email": "ghost@example.com"}
    )
    assert c1.status_code == 202 and c2.status_code == 202  # no oracle
    raw = identity_service.create_password_reset(owner_db, user)
    owner_db.commit()
    ok = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": raw, "new_password": "brand-new-password-1"},
    )
    assert ok.status_code == 200, ok.text
    c = login_client(client, email="dana@example.com", password="brand-new-password-1")
    assert c.get("/api/v1/auth/me").status_code == 200
    reuse = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": raw, "new_password": "another-password-22"},
    )
    assert reuse.status_code == 410


def test_validation_envelope(client) -> None:  # type: ignore[no-untyped-def]
    r = client.post(
        "/api/v1/auth/login", json={"email": "not-an-email", "password": "x"}
    )
    assert r.status_code == 422
    body = r.json()
    assert body["type"].endswith("validation-failed") and body["status"] == 422


def test_bearer_fallback_matches_cookie(client, owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    make_owner_user(email="erin@example.com")
    c = TestClient(client.app, base_url="http://test")
    r = c.post(
        "/api/v1/auth/login",
        json={"email": "erin@example.com", "password": "password-12345-abc"},
    )
    assert r.status_code == 200
    access = r.cookies.get("hos_access")
    assert access
    naked = TestClient(client.app, base_url="http://test")
    me = naked.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert me.status_code == 200, me.text


def test_sessions_list_and_revoke(client, owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    make_owner_user(email="fay@example.com")
    c = login_client(client, email="fay@example.com")
    sessions = c.get("/api/v1/auth/sessions").json()
    assert len(sessions) == 1 and sessions[0]["current"] is True
    sid = sessions[0]["id"]
    assert c.delete(f"/api/v1/auth/sessions/{sid}").status_code == 204
    assert c.get("/api/v1/auth/sessions").status_code == 401  # revoked mid-flight
