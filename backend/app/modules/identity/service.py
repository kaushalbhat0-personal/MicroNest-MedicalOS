"""Identity service: users, passwords, sessions, resets. Single source of
truth for authN rules. No tenant logic here (membership lives in tenancy)."""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.modules.identity.models import (
    AuthEvent,
    Credential,
    PasswordReset,
    Session,
    User,
)
from app.platform import ids
from app.platform.time import UTC
from app.platform.errors import AuthError, ConflictError, GoneError, SessionReuseError
from app.platform.security import passwords, tokens


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _now() -> datetime:
    return datetime.now(UTC)


def record_auth_event(
    db: DBSession,
    *,
    action: str,
    user_id: uuid.UUID | None,
    tenant_id: uuid.UUID | None = None,
    ip: str | None = None,
) -> None:
    db.add(
        AuthEvent(
            id=ids.uuid7(),
            user_id=user_id,
            tenant_id=tenant_id,
            action=action,
            ip=ip,
            created_at=_now(),
        )
    )


def get_user_by_email(db: DBSession, email: str) -> User | None:
    return db.execute(
        select(User).where(User.email == normalize_email(email))
    ).scalar_one_or_none()


def create_user(
    db: DBSession, *, email: str, display_name: str, password: str | None = None
) -> User:
    email_n = normalize_email(email)
    if get_user_by_email(db, email_n) is not None:
        raise ConflictError("email already registered")
    now = _now()
    user = User(
        id=ids.uuid7(),
        email=email_n,
        display_name=display_name,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.flush()
    if password is not None:
        set_password(db, user, password)
    return user


def set_password(db: DBSession, user: User, password: str) -> None:
    hashed = passwords.hash_password(password)
    cred = db.execute(
        select(Credential).where(
            Credential.user_id == user.id, Credential.type == "password"
        )
    ).scalar_one_or_none()
    now = _now()
    if cred is None:
        db.add(
            Credential(
                id=ids.uuid7(),
                user_id=user.id,
                type="password",
                secret_hash=hashed,
                created_at=now,
                updated_at=now,
            )
        )
    else:
        cred.secret_hash = hashed
        cred.updated_at = now
    user.updated_at = now


def authenticate(db: DBSession, *, email: str, password: str, ip: str | None) -> User:
    user = get_user_by_email(db, email)
    if user is None or not user.is_active:
        record_auth_event(db, action="login_failed", user_id=None, ip=ip)
        raise AuthError("invalid credentials")
    cred = db.execute(
        select(Credential).where(
            Credential.user_id == user.id, Credential.type == "password"
        )
    ).scalar_one_or_none()
    if cred is None or not passwords.verify_password(password, cred.secret_hash):
        record_auth_event(db, action="login_failed", user_id=user.id, ip=ip)
        raise AuthError("invalid credentials")
    if passwords.needs_rehash(cred.secret_hash):
        cred.secret_hash = passwords.hash_password(password)
        cred.updated_at = _now()
    record_auth_event(db, action="login_success", user_id=user.id, ip=ip)
    return user


def create_session(
    db: DBSession,
    user: User,
    *,
    ip: str | None,
    user_agent: str | None,
    refresh_days: int,
) -> tuple[Session, str]:
    secret = tokens.new_refresh_secret()
    now = _now()
    session = Session(
        id=ids.uuid7(),
        user_id=user.id,
        family_id=tokens.new_session_family(),
        refresh_hash=tokens.hash_refresh_secret(secret),
        created_at=now,
        expires_at=now + timedelta(days=refresh_days),
        last_used_at=now,
        revoked_at=None,
        revoked_reason=None,
        ip=ip,
        user_agent=(user_agent or "")[:300] or None,
    )
    db.add(session)
    return session, secret


def _revoke_family(
    db: DBSession, family_id: uuid.UUID, *, reason: str, exclude: uuid.UUID | None = None
) -> None:
    rows = db.execute(
        select(Session).where(Session.family_id == family_id)
    ).scalars().all()
    now = _now()
    for row in rows:
        if exclude is not None and row.id == exclude:
            continue
        if row.revoked_at is None:
            row.revoked_at = now
            row.revoked_reason = reason


def rotate_session(
    db: DBSession,
    *,
    session_id: uuid.UUID,
    presented_secret: str,
    ip: str | None,
    refresh_days: int,
) -> tuple[Session, str]:
    """Refresh rotation. Presenting an already-rotated secret means theft:
    revoke the whole family and fail closed."""
    presented_hash = tokens.hash_refresh_secret(presented_secret)
    current = db.get(Session, session_id)
    now = _now()
    if current is None:
        raise AuthError("invalid session")
    if current.refresh_hash != presented_hash:
        # Is it a rotated (old) secret? Check family for a revoked row mismatch.
        _revoke_family(db, current.family_id, reason="reuse_detected")
        record_auth_event(
            db, action="session_reuse_detected", user_id=current.user_id, ip=ip
        )
        raise SessionReuseError("session reuse detected; family revoked")
    if current.revoked_at is not None or current.expires_at <= now:
        raise AuthError("session expired")
    user = db.get(User, current.user_id)
    if user is None or not user.is_active:
        raise AuthError("invalid session")
    current.revoked_at = now
    current.revoked_reason = "rotated"
    new_secret = tokens.new_refresh_secret()
    nxt = Session(
        id=ids.uuid7(),
        user_id=current.user_id,
        family_id=current.family_id,
        refresh_hash=tokens.hash_refresh_secret(new_secret),
        created_at=now,
        expires_at=now + timedelta(days=refresh_days),
        last_used_at=now,
        revoked_at=None,
        revoked_reason=None,
        ip=ip,
        user_agent=current.user_agent,
    )
    db.add(nxt)
    current.last_used_at = now
    record_auth_event(db, action="session_refreshed", user_id=user.id, ip=ip)
    return nxt, new_secret


def revoke_session(db: DBSession, session: Session, *, reason: str = "logout") -> None:
    if session.revoked_at is None:
        session.revoked_at = _now()
        session.revoked_reason = reason
    record_auth_event(db, action="session_revoked", user_id=session.user_id)


def revoke_all_user_sessions(
    db: DBSession, user_id: uuid.UUID, *, reason: str
) -> int:
    rows = db.execute(
        select(Session).where(Session.user_id == user_id, Session.revoked_at.is_(None))
    ).scalars().all()
    now = _now()
    for row in rows:
        row.revoked_at = now
        row.revoked_reason = reason
    return len(rows)


def create_password_reset(db: DBSession, user: User) -> str:
    raw = secrets.token_urlsafe(48)
    now = _now()
    db.add(
        PasswordReset(
            id=ids.uuid7(),
            user_id=user.id,
            token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            expires_at=now + timedelta(hours=2),
            used_at=None,
            created_at=now,
        )
    )
    record_auth_event(db, action="reset_requested", user_id=user.id)
    return raw


def consume_password_reset(db: DBSession, *, token: str, new_password: str) -> User:
    digest = hashlib.sha256(token.encode()).hexdigest()
    row = db.execute(
        select(PasswordReset).where(PasswordReset.token_hash == digest)
    ).scalar_one_or_none()
    if row is None or row.used_at is not None or row.expires_at <= _now():
        raise GoneError("reset token invalid or expired")
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise GoneError("reset token invalid or expired")
    set_password(db, user, new_password)
    row.used_at = _now()
    revoke_all_user_sessions(db, user.id, reason="password_reset")
    record_auth_event(db, action="reset_completed", user_id=user.id)
    return user
