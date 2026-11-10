"""Email verification challenges for public signup (O1.1).

Lifecycle: signup/resend issues a single-use expiring challenge bound to
(user_id + normalized email snapshot); verify consumes it atomically and
marks the user verified. Raw tokens exist only in memory and in the
out-of-band delivery — never in the database, logs, audit, or API payloads.

Concurrency: consume takes a row lock (FOR UPDATE) so two simultaneous
verifies cannot both succeed; issue supersedes-then-inserts inside a
savepoint so two simultaneous resends leave exactly one live challenge.

Delivery boundary (O1.1 launch limitation): the challenge is enqueued on the
existing outbox/notification abstraction (template `verify_email`, refs
only). No production email provider exists in this slice (dev-console/none
adapters only). Until a real provider lands (deferred P8.1C/O4 work),
public signup on a provider-less deployment creates the account and the
challenge but cannot deliver the link — operators must not enable the
public signup route with NOTIFY_PROVIDER=none and expect delivery.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.modules.identity import service as identity_service
from app.modules.identity.models import EmailVerification, User
from app.platform import ids
from app.platform.errors import ForbiddenError, GoneError
from app.platform.time import UTC

VERIFY_TOKEN_TTL = timedelta(hours=24)
VERIFY_TEMPLATE = "verify_email"


def _now() -> datetime:
    return datetime.now(UTC)


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _pending_for_user(db: DBSession, user_id: uuid.UUID) -> list[EmailVerification]:
    return list(
        db.execute(
            select(EmailVerification).where(
                EmailVerification.user_id == user_id,
                EmailVerification.used_at.is_(None),
                EmailVerification.superseded_at.is_(None),
            )
        )
        .scalars()
        .all()
    )


def issue_challenge(
    db: DBSession, user: User, *, reason: str = "signup", ip: str | None = None
) -> tuple[EmailVerification, str | None]:
    """Supersede live challenges, insert a fresh one, enqueue delivery.

    Returns (row, raw). `raw` is None only when a concurrent issue won the
    race — the caller must then skip duplicate logging/delivery and reuse
    the winner's row. Enqueues exactly one notify per winning challenge.
    """
    from app.modules.notifications import service as notify_service
    from app.platform.ports.ports import NotifyRequest

    now = _now()
    email_n = identity_service.normalize_email(user.email)
    for stale in _pending_for_user(db, user.id):
        stale.superseded_at = now
    db.flush()

    raw = secrets.token_urlsafe(48)
    row = EmailVerification(
        id=ids.uuid7(),
        user_id=user.id,
        email=email_n,
        token_hash=_digest(raw),
        expires_at=now + VERIFY_TOKEN_TTL,
        used_at=None,
        superseded_at=None,
        created_at=now,
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError as exc:
        # A concurrent issue committed first; its row is now visible.
        # Our supersedes above touched only rows visible to us (older ones),
        # so exactly one live challenge survives.
        winner = _pending_for_user(db, user.id)
        if not winner:
            raise GoneError("verification unavailable; retry resend") from exc
        return winner[0], None
    notify_service.request_notification(
        db,
        NotifyRequest(
            channel="email",
            to_ref=str(user.id),
            template=VERIFY_TEMPLATE,
            locale="en",
            context_refs={"user_id": str(user.id), "verification_id": str(row.id)},
            tenant_id=None,
        ),
    )
    identity_service.record_auth_event(
        db,
        action=f"verification_{reason}",
        user_id=user.id,
        ip=ip,
    )
    return row, raw


def consume_challenge(db: DBSession, *, token: str, ip: str | None = None) -> User:
    """Consume a raw verification token. Single-use, expiring, email-bound.

    All failure modes (unknown/used/superseded/expired/bound-email-changed)
    raise the identical GoneError: no account oracle. Row lock makes
    concurrent consumption safe: exactly one succeeds.
    """
    digest = _digest(token)
    row = db.execute(
        select(EmailVerification).where(EmailVerification.token_hash == digest).with_for_update()
    ).scalar_one_or_none()
    now = _now()
    if (
        row is None
        or row.used_at is not None
        or row.superseded_at is not None
        or row.expires_at <= now
    ):
        raise GoneError("verification link invalid or expired")
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise GoneError("verification link invalid or expired")
    if identity_service.normalize_email(user.email) != row.email:
        # The account's email moved after issue (no such endpoint in O1.1,
        # but fail closed rather than verify a stale address).
        raise GoneError("verification link invalid or expired")
    row.used_at = now
    if user.email_verified_at is None:
        user.email_verified_at = now
        user.updated_at = now
    identity_service.record_auth_event(db, action="verification_consumed", user_id=user.id, ip=ip)
    return user


def is_verified(user: User) -> bool:
    return user.email_verified_at is not None


def require_verified_email(user: User) -> None:
    """O1.2 provisioning gate. Takes the server-resolved User object from
    get_current_user — never a client-supplied user_id. Fail-closed."""
    if not is_verified(user):
        raise ForbiddenError("email verification required")
