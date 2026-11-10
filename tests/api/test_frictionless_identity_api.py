"""O1.1R: frictionless identity alignment. Verification is optional.

Proves the revised journey: signup -> login -> me/tenants/portal-workspaces all
work while UNVERIFIED, password recovery works while unverified, and the
verify/resend machinery stays single-use + session-free (no weakening).
"""

from __future__ import annotations

from app.modules.identity import service as identity_service
from app.modules.identity import verification as verification_service
from tests.helpers import login_client

PASSWORD = "password-12345-abc"


def test_signup_then_login_while_unverified(client, owner_db) -> None:  # type: ignore[no-untyped-def]
    r = client.post(
        "/api/v1/auth/signup",
        json={
            "email": "free@example.com",
            "display_name": "Free User",
            "password": PASSWORD,
        },
    )
    assert r.status_code == 202, r.text
    assert r.json() == {"status": "accepted"}
    # Signup never issues a session (unchanged).
    assert "hos_access" not in r.cookies and "hos_refresh" not in r.cookies
    user = identity_service.get_user_by_email(owner_db, "free@example.com")
    assert user is not None and user.email_verified_at is None
    # Login works while unverified: no verification gate.
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "free@example.com", "password": PASSWORD},
    )
    assert login.status_code == 200, login.text
    assert login.json()["email_verified"] is False


def test_pre_provisioning_surfaces_open_while_unverified(
    client, owner_db, make_owner_user
) -> None:  # type: ignore[no-untyped-def]
    make_owner_user(email="unver@example.com")
    c = login_client(client, email="unver@example.com")
    me = c.get("/api/v1/auth/me")
    assert me.status_code == 200, me.text
    assert me.json()["email_verified"] is False
    mine = c.get("/api/v1/tenants/mine")
    assert mine.status_code == 200, mine.text
    assert mine.json() == []
    ws = c.get("/api/v1/portal/workspaces")
    assert ws.status_code == 200, ws.text
    # No production path here demands verification: the helper exists but no
    # route wires it (verified structurally by these 200s + the grep guard in
    # the report; behaviorally by this test).


def test_password_reset_available_while_unverified(
    client, owner_db, make_owner_user
) -> None:  # type: ignore[no-untyped-def]
    user = make_owner_user(email="unver-reset@example.com")
    assert user.email_verified_at is None
    req = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "unver-reset@example.com"},
    )
    assert req.status_code == 202, req.text
    raw = identity_service.create_password_reset(owner_db, user)
    owner_db.commit()
    ok = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": raw, "new_password": "brand-new-password-9"},
    )
    assert ok.status_code == 200, ok.text
    c = login_client(
        client, email="unver-reset@example.com", password="brand-new-password-9"
    )
    assert c.get("/api/v1/auth/me").json()["email_verified"] is False


def test_verification_stays_optional_single_use_and_session_free(
    client, owner_db, make_owner_user
) -> None:  # type: ignore[no-untyped-def]
    user = make_owner_user(email="opt-verify@example.com")
    _ch, raw = verification_service.issue_challenge(owner_db, user, reason="test")
    assert raw is not None
    owner_db.commit()
    ok = client.post("/api/v1/auth/verify", json={"token": raw})
    assert ok.status_code == 200 and ok.json() == {"status": "ok"}
    # Verify proves inbox access, not device intent: no session is issued.
    assert "hos_access" not in ok.cookies and "hos_refresh" not in ok.cookies
    reuse = client.post("/api/v1/auth/verify", json={"token": raw})
    assert reuse.status_code == 410
    owner_db.refresh(user)
    assert user.email_verified_at is not None
    # ...and the verified user logs in exactly like before.
    c = login_client(client, email="opt-verify@example.com")
    assert c.get("/api/v1/auth/me").json()["email_verified"] is True
