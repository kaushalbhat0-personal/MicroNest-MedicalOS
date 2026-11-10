"""O1.1: public signup + email verification. Real Postgres, RLS role, no oracles."""

from __future__ import annotations

import threading

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.modules.identity import service as identity_service
from app.modules.identity import verification as verification_service
from app.modules.identity.models import EmailVerification, User
from app.modules.tenancy import service as tenancy_service
from app.platform.errors import ForbiddenError
from tests.conftest import TEST_OWNER_URL

PASSWORD = "password-12345-abc"


def _pending(owner_db, user_id):  # type: ignore[no-untyped-def]
    return [
        r
        for r in owner_db.execute(
            select(EmailVerification).where(EmailVerification.user_id == user_id)
        )
        .scalars()
        .all()
        if r.used_at is None and r.superseded_at is None
    ]


def _issue_raw(owner_db, user):  # type: ignore[no-untyped-def]
    """Same code path as the endpoint; returns the raw token (HTTP never does)."""
    _ch, raw = verification_service.issue_challenge(owner_db, user, reason="test")
    assert raw is not None
    owner_db.commit()
    return raw


# ---------- A. Identity ----------


def test_signup_valid_creates_unverified_user(
    client, owner_db, make_owner_user
) -> None:  # type: ignore[no-untyped-def]
    r = client.post(
        "/api/v1/auth/signup",
        json={
            "email": "new@example.com",
            "display_name": "New Doc",
            "password": PASSWORD,
        },
    )
    assert r.status_code == 202, r.text
    assert r.json() == {"status": "accepted"}
    # No session is issued on signup.
    assert "hos_access" not in r.cookies and "hos_refresh" not in r.cookies
    user = identity_service.get_user_by_email(owner_db, "new@example.com")
    assert user is not None and user.email_verified_at is None
    assert user.is_platform_admin is False and user.is_active is True
    assert len(_pending(owner_db, user.id)) == 1
    # Delivery enqueued on the existing outbox abstraction, refs only.
    rows = owner_db.execute(
        text(
            "SELECT tenant_id, payload::text AS p FROM outbox_events "
            "WHERE type='notification.requested' AND payload->>'template'='verify_email'"
        )
    ).all()
    assert len(rows) == 1 and rows[0][0] is None
    assert str(user.id) in rows[0][1] and "token" not in rows[0][1].lower()
    # No tenant, no membership, no platform privilege from signup.
    assert tenancy_service.user_memberships(owner_db, user.id) == []
    assert owner_db.execute(text("SELECT count(*) FROM tenants")).scalar() == 0


def test_signup_duplicate_is_indistinguishable(
    client, owner_db, make_owner_user
) -> None:  # type: ignore[no-untyped-def]
    first = client.post(
        "/api/v1/auth/signup",
        json={"email": "dup@example.com", "display_name": "Dup", "password": PASSWORD},
    )
    before_users = owner_db.execute(text("SELECT count(*) FROM users")).scalar()
    before_ch = owner_db.execute(
        text("SELECT count(*) FROM email_verifications")
    ).scalar()
    second = client.post(
        "/api/v1/auth/signup",
        json={
            "email": "dup@example.com",
            "display_name": "Someone Else",
            "password": PASSWORD,
        },
    )
    assert first.status_code == 202 and second.status_code == 202
    assert first.json() == second.json() == {"status": "accepted"}
    assert owner_db.execute(text("SELECT count(*) FROM users")).scalar() == before_users
    assert (
        owner_db.execute(text("SELECT count(*) FROM email_verifications")).scalar()
        == before_ch
    )


def test_signup_normalizes_email(client, owner_db) -> None:  # type: ignore[no-untyped-def]
    r = client.post(
        "/api/v1/auth/signup",
        json={
            "email": "  ALICE@Example.COM ",
            "display_name": "Alice",
            "password": PASSWORD,
        },
    )
    assert r.status_code == 202, r.text
    user = identity_service.get_user_by_email(owner_db, "alice@example.com")
    assert user is not None and user.email == "alice@example.com"
    again = client.post(
        "/api/v1/auth/signup",
        json={
            "email": "Alice@example.com",
            "display_name": "Alice 2",
            "password": PASSWORD,
        },
    )
    assert again.status_code == 202
    assert owner_db.execute(text("SELECT count(*) FROM users")).scalar() == 1


def test_signup_rejects_weak_password_without_oracle_change(client, owner_db) -> None:  # type: ignore[no-untyped-def]
    r = client.post(
        "/api/v1/auth/signup",
        json={"email": "weak@example.com", "display_name": "Weak", "password": "short"},
    )
    assert r.status_code == 422
    # Shape validation happens before any write: no user, no side effects.
    assert identity_service.get_user_by_email(owner_db, "weak@example.com") is None


def test_signup_throttle_stays_202(client, owner_db) -> None:  # type: ignore[no-untyped-def]
    bodies = set()
    for i in range(11):
        r = client.post(
            "/api/v1/auth/signup",
            json={
                "email": f"throttle{i}@example.com",
                "display_name": "T",
                "password": PASSWORD,
            },
        )
        assert r.status_code == 202, r.text
        bodies.add(r.json()["status"])
    assert bodies == {"accepted"}


def test_signup_does_not_log_in(client, owner_db) -> None:  # type: ignore[no-untyped-def]
    client.post(
        "/api/v1/auth/signup",
        json={
            "email": "nologin@example.com",
            "display_name": "No",
            "password": PASSWORD,
        },
    )
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_reports_verification_status(client, owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    from tests.helpers import login_client

    user = make_owner_user(email="status@example.com")
    raw = _issue_raw(owner_db, user)
    c = login_client(client, email="status@example.com")
    assert c.get("/api/v1/auth/me").json()["email_verified"] is False
    assert c.post("/api/v1/auth/verify", json={"token": raw}).status_code == 200
    assert c.get("/api/v1/auth/me").json()["email_verified"] is True


# ---------- B. Verification ----------


def test_verify_valid_then_reuse_fails(client, owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    user = make_owner_user(email="v@example.com")
    raw = _issue_raw(owner_db, user)
    ok = client.post("/api/v1/auth/verify", json={"token": raw})
    assert ok.status_code == 200 and ok.json() == {"status": "ok"}
    owner_db.refresh(user)
    assert user.email_verified_at is not None
    ch = owner_db.execute(
        select(EmailVerification).where(EmailVerification.user_id == user.id)
    ).scalar_one()
    assert ch.used_at is not None
    reuse = client.post("/api/v1/auth/verify", json={"token": raw})
    assert reuse.status_code == 410


def test_verify_invalid_expired_share_envelope(
    client, owner_db, make_owner_user
) -> None:  # type: ignore[no-untyped-def]
    user = make_owner_user(email="w@example.com")
    raw = _issue_raw(owner_db, user)
    bad = client.post("/api/v1/auth/verify", json={"token": "bogus-token"})
    # Expire the real challenge without consuming it.
    ch = owner_db.execute(
        select(EmailVerification).where(EmailVerification.user_id == user.id)
    ).scalar_one()
    from datetime import datetime, timezone

    ch.expires_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
    owner_db.commit()
    expired = client.post("/api/v1/auth/verify", json={"token": raw})
    assert bad.status_code == 410 and expired.status_code == 410
    assert bad.json()["type"] == expired.json()["type"]
    owner_db.refresh(user)
    assert user.email_verified_at is None


def test_verify_throttle_matches_bad_token(client) -> None:  # type: ignore[no-untyped-def]
    first = client.post("/api/v1/auth/verify", json={"token": "bogus"})
    assert first.status_code == 410
    for _ in range(10):
        r = client.post("/api/v1/auth/verify", json={"token": "bogus"})
        assert r.status_code == 410
        assert r.json()["type"] == first.json()["type"]


def test_resend_supersedes_old_token(client, owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    user = make_owner_user(email="s@example.com")
    old_raw = _issue_raw(owner_db, user)
    old_id = _pending(owner_db, user.id)[0].id
    r = client.post("/api/v1/auth/verify/resend", json={"email": "s@example.com"})
    assert r.status_code == 202 and r.json() == {"status": "accepted"}
    live = _pending(owner_db, user.id)
    assert len(live) == 1 and live[0].id != old_id
    assert (
        client.post("/api/v1/auth/verify", json={"token": old_raw}).status_code == 410
    )


def test_verify_email_binding_rejects_moved_account(
    client, owner_db, make_owner_user
) -> None:  # type: ignore[no-untyped-def]
    user = make_owner_user(email="bind@example.com")
    raw = _issue_raw(owner_db, user)
    user.email = "moved@example.com"
    owner_db.commit()
    assert client.post("/api/v1/auth/verify", json={"token": raw}).status_code == 410
    owner_db.refresh(user)
    assert user.email_verified_at is None


def test_concurrent_verify_single_winner(owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    user = make_owner_user(email="race@example.com")
    _ch, raw = verification_service.issue_challenge(owner_db, user, reason="test")
    assert raw is not None
    owner_db.commit()
    gate = threading.Barrier(3)
    outcomes: list[str] = []

    def worker() -> None:
        engine = create_engine(TEST_OWNER_URL)
        Session = sessionmaker(bind=engine)
        s = Session()
        try:
            gate.wait(timeout=30)
            verification_service.consume_challenge(s, token=raw)
            s.commit()
            outcomes.append("ok")
        except Exception:
            s.rollback()
            outcomes.append("gone")
        finally:
            s.close()
            engine.dispose()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    gate.wait(timeout=30)
    for t in threads:
        t.join(timeout=60)
    assert sorted(outcomes) == ["gone", "ok"]
    owner_db.expire_all()
    assert verification_service.is_verified(
        owner_db.execute(
            select(User).where(User.email == "race@example.com")
        ).scalar_one()
    )


# ---------- C. Resend ----------


def test_resend_unknown_email_is_indistinguishable(client) -> None:  # type: ignore[no-untyped-def]
    known = client.post(
        "/api/v1/auth/verify/resend", json={"email": "ghost@example.com"}
    )
    assert known.status_code == 202 and known.json() == {"status": "accepted"}


def test_resend_verified_user_creates_nothing(
    client, owner_db, make_owner_user
) -> None:  # type: ignore[no-untyped-def]
    user = make_owner_user(email="done@example.com")
    raw = _issue_raw(owner_db, user)
    assert client.post("/api/v1/auth/verify", json={"token": raw}).status_code == 200
    before = owner_db.execute(text("SELECT count(*) FROM email_verifications")).scalar()
    r = client.post("/api/v1/auth/verify/resend", json={"email": "done@example.com"})
    assert r.status_code == 202
    assert (
        owner_db.execute(text("SELECT count(*) FROM email_verifications")).scalar()
        == before
    )


def test_resend_per_email_limit_enforced_silently(
    client, owner_db, make_owner_user
) -> None:  # type: ignore[no-untyped-def]
    user = make_owner_user(email="rl@example.com")
    _issue_raw(owner_db, user)
    first_live = _pending(owner_db, user.id)[0].id
    for _ in range(2):
        r = client.post("/api/v1/auth/verify/resend", json={"email": "rl@example.com"})
        assert r.status_code == 202 and r.json() == {"status": "accepted"}
    limited = client.post(
        "/api/v1/auth/verify/resend", json={"email": "rl@example.com"}
    )
    assert limited.status_code == 202 and limited.json() == {"status": "accepted"}
    live = _pending(owner_db, user.id)
    assert len(live) == 1 and live[0].id != first_live  # limit hit: winner stands


def test_concurrent_resend_single_pending(owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    user = make_owner_user(email="rrace@example.com")
    owner_db.commit()
    gate = threading.Barrier(3)
    winners: list[str] = []

    def worker() -> None:
        engine = create_engine(TEST_OWNER_URL)
        Session = sessionmaker(bind=engine)
        s = Session()
        try:
            gate.wait(timeout=30)
            db_user = s.execute(
                select(User).where(User.email == "rrace@example.com")
            ).scalar_one()
            _ch, _raw = verification_service.issue_challenge(s, db_user, reason="test")
            s.commit()
            winners.append("ok")
        except Exception:
            s.rollback()
            winners.append("gone")
        finally:
            s.close()
            engine.dispose()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    gate.wait(timeout=30)
    for t in threads:
        t.join(timeout=60)
    assert winners.count("ok") >= 1
    owner_db.expire_all()
    assert len(_pending(owner_db, user.id)) == 1


# ---------- D. Authorization ----------


def test_unauthenticated_me_is_401(client) -> None:  # type: ignore[no-untyped-def]
    assert client.get("/api/v1/auth/me").status_code == 401


def test_require_verified_email_gate(owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    user = make_owner_user(email="gate@example.com")
    with pytest.raises(ForbiddenError):
        verification_service.require_verified_email(user)
    raw = _issue_raw(owner_db, user)
    verification_service.consume_challenge(owner_db, token=raw)
    owner_db.commit()
    owner_db.refresh(user)
    verification_service.require_verified_email(user)  # consumed -> passes


def test_verify_token_is_bearer_capability(client, owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    from tests.helpers import login_client

    a = make_owner_user(email="cap-a@example.com")
    b = make_owner_user(email="cap-b@example.com")
    raw = _issue_raw(owner_db, a)
    cb = login_client(client, email="cap-b@example.com")
    # Logged in as B, presenting A's emailed token: verifies A, not B.
    assert cb.post("/api/v1/auth/verify", json={"token": raw}).status_code == 200
    owner_db.refresh(a)
    owner_db.refresh(b)
    assert a.email_verified_at is not None and b.email_verified_at is None
    assert verification_service.is_verified(a) and not verification_service.is_verified(
        b
    )


def test_signup_creates_no_tenant_membership_or_admin(client, owner_db) -> None:  # type: ignore[no-untyped-def]
    client.post(
        "/api/v1/auth/signup",
        json={
            "email": "plain@example.com",
            "display_name": "Plain",
            "password": PASSWORD,
        },
    )
    user = identity_service.get_user_by_email(owner_db, "plain@example.com")
    assert user is not None
    assert user.is_platform_admin is False
    assert tenancy_service.user_memberships(owner_db, user.id) == []
    assert owner_db.execute(text("SELECT count(*) FROM tenants")).scalar() == 0
    assert owner_db.execute(text("SELECT count(*) FROM memberships")).scalar() == 0


# ---------- E. Data safety ----------


def test_no_raw_token_at_rest(client, owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    user = make_owner_user(email="rest@example.com")
    raw = _issue_raw(owner_db, user)
    (stored_hash,) = owner_db.execute(
        select(EmailVerification.token_hash).where(EmailVerification.user_id == user.id)
    ).one()
    assert stored_hash != raw and len(stored_hash) == 64
    assert (
        owner_db.execute(
            text("SELECT count(*) FROM email_verifications WHERE token_hash = :raw"),
            {"raw": raw},
        ).scalar()
        == 0
    )
    (payload,) = owner_db.execute(
        text(
            "SELECT payload::text FROM outbox_events "
            "WHERE payload->>'template'='verify_email' ORDER BY occurred_at DESC LIMIT 1"
        )
    ).one()
    assert raw not in payload
    events = owner_db.execute(
        text("SELECT action, user_id::text FROM auth_events")
    ).all()
    assert events and not any(raw in str(row) for row in events)


def test_no_raw_token_in_logs_except_dev_marker(
    client, owner_db, make_owner_user, caplog
) -> None:  # type: ignore[no-untyped-def]
    import logging

    user = make_owner_user(email="logs@example.com")
    with caplog.at_level(logging.INFO):
        _ch, raw = verification_service.issue_challenge(owner_db, user, reason="test")
        owner_db.commit()
        assert raw is not None
        client.post("/api/v1/auth/verify", json={"token": raw})
    leaking = [r for r in caplog.records if raw in r.getMessage()]
    assert all("DEV-ONLY" in r.getMessage() for r in leaking)


def test_signup_rejects_bad_shape(client) -> None:  # type: ignore[no-untyped-def]
    assert (
        client.post(
            "/api/v1/auth/signup", json={"email": "x", "password": "y"}
        ).status_code
        == 422
    )
    assert client.post("/api/v1/auth/verify", json={"token": ""}).status_code == 422
