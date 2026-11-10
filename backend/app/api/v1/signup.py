"""Public signup + email verification (O1.1). No tenant, no session.

- POST /signup: always 202 (new, duplicate, throttled are indistinguishable).
  Creates the account via the existing identity service, issues a
  verification challenge, enqueues delivery. Never logs the user in, never
  creates a tenant/membership, never grants platform admin.
- POST /verify: consumes a raw token. 200 once; every failure mode is the
  identical 410 (no account oracle). No session is issued.
- POST /verify/resend: always 202. Per-IP + per-email throttles. A new
  challenge supersedes prior ones.

Raw tokens travel in the POST body only. They are hashed before lookup and
never returned, never stored, and never logged except for one explicitly
gated DEV-ONLY server line (dev/test + DEV_NOTIFICATIONS_ALLOW only).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.api.deps import get_db
from app.modules.identity import schemas as S
from app.modules.identity import service as identity_service
from app.modules.identity import verification as verification_service
from app.platform.errors import ConflictError, GoneError
from app.platform.logging_setup import get_logger
from app.platform.ratelimit import limiter, normalize_key

router = APIRouter(prefix="/auth", tags=["auth"])

log = get_logger(__name__)


def _dev_log_challenge(settings: object, raw: str) -> None:
    """DEV-ONLY delivery surrogate: print the verify link to the server log.

    Unreachable in preview/prod: Settings validation forbids
    DEV_NOTIFICATIONS_ALLOW outside dev/test (config.py), so this branch can
    never execute where real user data flows. O1.1 has no production email
    provider; without this, the dev/test signup loop could not be closed.
    """
    env = getattr(settings, "ENV", "")
    allow = bool(getattr(settings, "DEV_NOTIFICATIONS_ALLOW", False))
    if env in ("dev", "test") and allow:
        log.info("DEV-ONLY verification link (no email provider in O1.1): /verify?token=%s", raw)


@router.post("/signup", status_code=202)
def signup(
    body: S.SignupRequest,
    request: Request,
    db: DBSession = Depends(get_db),  # noqa: B008
) -> dict[str, str]:
    from app.api.deps import get_cached_settings

    settings = get_cached_settings()
    ip = request.client.host if request.client else "unknown"
    if not limiter.allow(
        scope="signup:ip",
        key=normalize_key(ip),
        limit=settings.SIGNUP_IP_LIMIT_PER_MIN,
        window_seconds=60,
    ):
        return {"status": "accepted"}
    # Duplicate path sends no mail and creates nothing: identical 202, so
    # signup can neither enumerate accounts nor bomb inboxes.
    if identity_service.get_user_by_email(db, str(body.email)) is not None:
        return {"status": "accepted"}
    try:
        with db.begin_nested():
            user = identity_service.create_user(
                db,
                email=str(body.email),
                display_name=body.display_name,
                password=body.password,
            )
            db.flush()
            _, raw = verification_service.issue_challenge(db, user, reason="signup", ip=ip)
    except (ConflictError, IntegrityError):
        # Lost a creation race with another signup: same observable 202.
        return {"status": "accepted"}
    if raw is not None:
        _dev_log_challenge(settings, raw)
    if settings.NOTIFY_PROVIDER == "none":
        # Explicit launch limitation: account + challenge exist, but no
        # provider can deliver the link. No account signal leaks (same 202).
        log.warning("signup accepted while NOTIFY_PROVIDER=none: verification cannot be delivered")
    return {"status": "accepted"}


@router.post("/verify")
def verify(
    body: S.VerifyRequest,
    request: Request,
    db: DBSession = Depends(get_db),  # noqa: B008
) -> dict[str, str]:
    from app.api.deps import get_cached_settings

    settings = get_cached_settings()
    ip = request.client.host if request.client else "unknown"
    if not limiter.allow(
        scope="verify:ip",
        key=normalize_key(ip),
        limit=settings.VERIFY_IP_LIMIT_PER_MIN,
        window_seconds=60,
    ):
        # No oracle: throttled guesses look exactly like bad tokens.
        raise GoneError("verification link invalid or expired")
    verification_service.consume_challenge(db, token=body.token, ip=ip)
    # Deliberately no session: verification proves inbox access, not device
    # intent. The user signs in normally afterwards.
    return {"status": "ok"}


@router.post("/verify/resend", status_code=202)
def verify_resend(
    body: S.VerifyResendRequest,
    request: Request,
    db: DBSession = Depends(get_db),  # noqa: B008
) -> dict[str, str]:
    from app.api.deps import get_cached_settings

    settings = get_cached_settings()
    ip = request.client.host if request.client else "unknown"
    ip_ok = limiter.allow(
        scope="verify-resend:ip",
        key=normalize_key(ip),
        limit=settings.VERIFY_RESEND_IP_LIMIT_PER_MIN,
        window_seconds=60,
    )
    email_ok = limiter.allow(
        scope="verify-resend:email",
        key=normalize_key(body.email),
        limit=settings.VERIFY_RESEND_EMAIL_LIMIT_PER_HOUR,
        window_seconds=3600,
    )
    # No oracle: every path — unknown email, throttled, verified, inactive —
    # returns the identical 202 with no side channel.
    user = identity_service.get_user_by_email(db, str(body.email))
    if (
        user is not None
        and user.is_active
        and ip_ok
        and email_ok
        and not verification_service.is_verified(user)
    ):
        _, raw = verification_service.issue_challenge(db, user, reason="resend", ip=ip)
        if raw is not None:
            _dev_log_challenge(settings, raw)
    return {"status": "accepted"}
