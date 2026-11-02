"""Identity service: auth, sessions, rotation/reuse, reset, revocation."""

import pytest

from app.modules.identity import service
from app.platform.errors import AuthError, ConflictError, GoneError, SessionReuseError


def test_create_and_authenticate(owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    user = make_owner_user(email="auth1@example.com")
    authed = service.authenticate(
        owner_db, email="auth1@example.com", password="password-12345-abc", ip="1.2.3.4"
    )
    assert authed.id == user.id


def test_authenticate_rejects_wrong_password(owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    make_owner_user(email="auth2@example.com")
    with pytest.raises(AuthError):
        service.authenticate(
            owner_db, email="auth2@example.com", password="wrong-password-xyz", ip=None
        )


def test_authenticate_unknown_user_no_oracle(owner_db) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(AuthError):
        service.authenticate(
            owner_db, email="nobody@example.com", password="whatever-password", ip=None
        )


def test_duplicate_email_conflict(owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    make_owner_user(email="dup@example.com")
    with pytest.raises(ConflictError):
        service.create_user(
            owner_db,
            email="DUP@example.com",
            display_name="x",
            password="password-12345-abc",
        )


def test_email_normalized_lower(owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    user = make_owner_user(email="MiXeD@example.com")
    assert user.email == "mixed@example.com"


def test_session_rotation_and_reuse_detection(owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    user = make_owner_user()
    session, secret = service.create_session(
        owner_db, user, ip=None, user_agent=None, refresh_days=30
    )
    owner_db.commit()
    nxt, new_secret = service.rotate_session(
        owner_db,
        session_id=session.id,
        presented_secret=secret,
        ip=None,
        refresh_days=30,
    )
    owner_db.commit()
    assert nxt.family_id == session.family_id and new_secret != secret
    # Replaying the OLD secret must revoke the whole family.
    with pytest.raises(SessionReuseError):
        service.rotate_session(
            owner_db,
            session_id=session.id,
            presented_secret=secret,
            ip=None,
            refresh_days=30,
        )
    owner_db.commit()
    from sqlalchemy import select

    from app.modules.identity.models import Session as SessionRow

    rows = (
        owner_db.execute(
            select(SessionRow).where(SessionRow.family_id == session.family_id)
        )
        .scalars()
        .all()
    )
    assert rows and all(r.revoked_at is not None for r in rows)


def test_password_reset_invalidates_sessions(owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    user = make_owner_user()
    service.create_session(owner_db, user, ip=None, user_agent=None, refresh_days=30)
    token = service.create_password_reset(owner_db, user)
    owner_db.commit()
    service.consume_password_reset(
        owner_db, token=token, new_password="brand-new-password-1"
    )
    owner_db.commit()
    # Old password dead, new works.
    with pytest.raises(AuthError):
        service.authenticate(
            owner_db, email=user.email, password="password-12345-abc", ip=None
        )
    authed = service.authenticate(
        owner_db, email=user.email, password="brand-new-password-1", ip=None
    )
    assert authed.id == user.id
    # Token single-use.
    with pytest.raises(GoneError):
        service.consume_password_reset(
            owner_db, token=token, new_password="another-password-22"
        )


def test_deactivated_user_cannot_auth(owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    user = make_owner_user()
    user.is_active = False
    owner_db.commit()
    with pytest.raises(AuthError):
        service.authenticate(
            owner_db, email=user.email, password="password-12345-abc", ip=None
        )


def test_short_password_rejected() -> None:
    with pytest.raises(ValueError):
        __import__(
            "app.platform.security.passwords", fromlist=["hash_password"]
        ).hash_password("short")


def test_revoke_all(owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    user = make_owner_user()
    service.create_session(owner_db, user, ip=None, user_agent=None, refresh_days=30)
    service.create_session(owner_db, user, ip=None, user_agent=None, refresh_days=30)
    n = service.revoke_all_user_sessions(owner_db, user.id, reason="test")
    assert n == 2
