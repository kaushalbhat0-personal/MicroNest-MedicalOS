"""Native JSON authentication for desktop clients.

Reuses identity sessions + JWT access tokens. Does not set browser cookies.
Browser cookie endpoints in auth.py / account.py remain unchanged.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session as DBSession

from app.api.deps import get_cached_settings, get_current_user, get_db
from app.api.errors import unauthorized_response
from app.api.v1._shared import tenant_options
from app.modules.identity import schemas as S
from app.modules.identity import service as identity_service
from app.modules.identity.models import Session as SessionRow
from app.modules.identity.models import User
from app.platform import db as dbmod
from app.platform.errors import AuthError
from app.platform.ratelimit import limiter, normalize_key
from app.platform.security import tokens as token_util

router = APIRouter(prefix="/auth/native", tags=["auth-native"])


def _issue_native_tokens(
    *,
    db: DBSession,
    user: User,
    session: SessionRow,
    refresh_secret: str,
) -> S.NativeTokenResponse:
    settings = get_cached_settings()
    access = token_util.create_access_token(
        user_id=user.id,
        session_id=session.id,
        secret=settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
        minutes=settings.ACCESS_TOKEN_MINUTES,
    )
    refresh = f"{session.id}.{refresh_secret}"
    platform = session.client_platform or "windows"
    # Memberships RLS: user_id = app.user_id OR tenant_id = app.tenant_id.
    # Set actor so tenant_options can see the caller's memberships.
    db.execute(text("SELECT set_config('app.user_id', :a, true)"), {"a": str(user.id)})
    dbmod.actor_ctx.set(str(user.id))
    return S.NativeTokenResponse(
        access_token=access,
        refresh_token=refresh,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_MINUTES * 60,
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_platform_admin=user.is_platform_admin,
        email_verified=user.email_verified_at is not None,
        tenants=tenant_options(db, user),
        session_id=session.id,
        client_platform=platform,
    )


def _parse_refresh_token(raw: str) -> tuple[uuid.UUID, str] | None:
    if "." not in raw:
        return None
    sid_raw, _, secret = raw.partition(".")
    if not sid_raw or not secret:
        return None
    try:
        return uuid.UUID(sid_raw), secret
    except ValueError:
        return None


@router.post("/login", response_model=S.NativeTokenResponse)
def native_login(
    body: S.NativeLoginRequest,
    request: Request,
    db: DBSession = Depends(get_db),  # noqa: B008
) -> object:
    settings = get_cached_settings()
    ip = request.client.host if request.client else None
    if not limiter.allow(
        scope="login:ip",
        key=normalize_key(ip),
        limit=settings.LOGIN_IP_LIMIT_PER_MIN,
        window_seconds=60,
    ):
        return unauthorized_response("too many attempts")
    if not limiter.allow(
        scope="login:account",
        key=normalize_key(body.email),
        limit=settings.LOGIN_ACCOUNT_LIMIT_PER_MIN,
        window_seconds=60,
    ):
        return unauthorized_response("too many attempts")
    try:
        user = identity_service.authenticate(
            db, email=str(body.email), password=body.password, ip=ip
        )
    except AuthError:
        return unauthorized_response()
    ua = request.headers.get("user-agent")
    session, secret = identity_service.create_session(
        db,
        user,
        ip=ip,
        user_agent=ua,
        refresh_days=settings.REFRESH_TOKEN_DAYS,
        client_platform=body.client_platform,
        device_label=body.device_label,
        client_instance_id=body.client_instance_id,
    )
    return _issue_native_tokens(db=db, user=user, session=session, refresh_secret=secret)


@router.post("/refresh", response_model=S.NativeTokenResponse)
def native_refresh(
    body: S.NativeRefreshRequest,
    request: Request,
    db: DBSession = Depends(get_db),  # noqa: B008
) -> object:
    settings = get_cached_settings()
    ip = request.client.host if request.client else None
    if not limiter.allow(
        scope="refresh:ip",
        key=normalize_key(ip),
        limit=settings.REFRESH_IP_LIMIT_PER_MIN,
        window_seconds=60,
    ):
        return unauthorized_response("too many attempts")
    parsed = _parse_refresh_token(body.refresh_token)
    if parsed is None:
        return unauthorized_response("refresh required")
    sid, secret = parsed
    try:
        session, new_secret = identity_service.rotate_session(
            db,
            session_id=sid,
            presented_secret=secret,
            ip=ip,
            refresh_days=settings.REFRESH_TOKEN_DAYS,
        )
    except AuthError:
        return unauthorized_response()
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        return unauthorized_response()
    return _issue_native_tokens(db=db, user=user, session=session, refresh_secret=new_secret)


@router.post("/logout", status_code=204, response_model=None)
def native_logout(
    user_session: tuple[User, SessionRow] = Depends(get_current_user),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> None:
    """Revoke the current session. Access JWTs for this sid fail on next request
    because get_current_user checks sessions.revoked_at."""
    _, session = user_session
    identity_service.revoke_session(db, session, reason="logout")
