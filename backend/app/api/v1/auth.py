"""Auth endpoints. Login, refresh rotation, logout, me, password reset.
Rate-limited. Tokens travel in HttpOnly cookies; Bearer fallback accepted.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.api.deps import get_cached_settings, get_current_user, get_db
from app.api.v1._shared import tenant_options
from app.modules.identity import schemas as S
from app.modules.identity import service as identity_service
from app.modules.identity.models import Session as SessionRow
from app.modules.identity.models import User
from app.modules.notifications import service as notify_service
from app.modules.tenancy import service as tenancy_service
from app.platform.authz.permissions import P
from app.platform.errors import AuthError
from app.platform.ports.ports import NotifyRequest
from app.platform.ratelimit import limiter
from app.platform.security import cookies as cookie_util
from app.platform.security import tokens as token_util

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_pair(
    response: Response, db: DBSession, user: User, *, ip: str | None, ua: str | None
) -> SessionRow:
    settings = get_cached_settings()
    session, refresh_secret = identity_service.create_session(
        db, user, ip=ip, user_agent=ua, refresh_days=settings.REFRESH_TOKEN_DAYS
    )
    access = token_util.create_access_token(
        user_id=user.id,
        session_id=session.id,
        secret=settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
        minutes=settings.ACCESS_TOKEN_MINUTES,
    )
    cookie_util.set_auth_cookies(
        response,
        access=access,
        refresh=f"{session.id}.{refresh_secret}",
        secure=settings.COOKIE_SECURE,
        domain=settings.COOKIE_DOMAIN,
        refresh_days=settings.REFRESH_TOKEN_DAYS,
    )
    return session


@router.post("/login", response_model=S.MeResponse)
def login(
    body: S.LoginRequest, request: Request, response: Response,
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.MeResponse:
    settings = get_cached_settings()
    ip = request.client.host if request.client else None
    if not limiter.allow(
        scope="login:ip", key=ip or "unknown",
        limit=settings.LOGIN_IP_LIMIT_PER_MIN, window_seconds=60,
    ):
        raise AuthError("too many attempts")
    if not limiter.allow(
        scope="login:account", key=body.email.lower(),
        limit=settings.LOGIN_ACCOUNT_LIMIT_PER_MIN, window_seconds=60,
    ):
        raise AuthError("too many attempts")
    user = identity_service.authenticate(
        db, email=str(body.email), password=body.password, ip=ip
    )
    ua = request.headers.get("user-agent")
    _issue_pair(response, db, user, ip=ip, ua=ua)
    return S.MeResponse(
        id=user.id, email=user.email, display_name=user.display_name,
        is_platform_admin=user.is_platform_admin,
        tenants=tenant_options(db, user),
    )


@router.post("/refresh", response_model=S.MeResponse)
def refresh(
    request: Request, response: Response,
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.MeResponse:
    settings = get_cached_settings()
    raw = request.cookies.get(cookie_util.REFRESH_COOKIE)
    if not raw or "." not in raw:
        raise AuthError("refresh required")
    sid_raw, _, secret = raw.partition(".")
    try:
        sid = uuid.UUID(sid_raw)
    except ValueError as exc:
        raise AuthError("invalid session") from exc
    ip = request.client.host if request.client else None
    session, new_secret = identity_service.rotate_session(
        db, session_id=sid, presented_secret=secret, ip=ip,
        refresh_days=settings.REFRESH_TOKEN_DAYS,
    )
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise AuthError("account inactive")
    access = token_util.create_access_token(
        user_id=user.id, session_id=session.id, secret=settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM, minutes=settings.ACCESS_TOKEN_MINUTES,
    )
    cookie_util.set_auth_cookies(
        response, access=access, refresh=f"{session.id}.{new_secret}",
        secure=settings.COOKIE_SECURE, domain=settings.COOKIE_DOMAIN,
        refresh_days=settings.REFRESH_TOKEN_DAYS,
    )
    return S.MeResponse(
        id=user.id, email=user.email, display_name=user.display_name,
        is_platform_admin=user.is_platform_admin,
        tenants=tenant_options(db, user),
    )
