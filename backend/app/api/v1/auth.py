"""Auth endpoints. Login, refresh rotation, logout, me, password reset.
Rate-limited. Tokens travel in HttpOnly cookies; Bearer fallback accepted.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session as DBSession

from app.api.deps import get_cached_settings, get_db
from app.api.errors import unauthorized_response
from app.api.v1._shared import issue_session_pair, tenant_options
from app.modules.identity import schemas as S
from app.modules.identity import service as identity_service
from app.modules.identity.models import User
from app.platform.errors import AuthError
from app.platform.ratelimit import limiter
from app.platform.security import cookies as cookie_util

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=S.MeResponse)
def login(
    body: S.LoginRequest,
    request: Request,
    response: Response,
    db: DBSession = Depends(get_db),  # noqa: B008
) -> object:
    settings = get_cached_settings()
    ip = request.client.host if request.client else None
    if not limiter.allow(
        scope="login:ip",
        key=ip or "unknown",
        limit=settings.LOGIN_IP_LIMIT_PER_MIN,
        window_seconds=60,
    ):
        return unauthorized_response("too many attempts")
    if not limiter.allow(
        scope="login:account",
        key=body.email.lower(),
        limit=settings.LOGIN_ACCOUNT_LIMIT_PER_MIN,
        window_seconds=60,
    ):
        return unauthorized_response("too many attempts")
    try:
        user = identity_service.authenticate(
            db, email=str(body.email), password=body.password, ip=ip
        )
    except AuthError:
        # Return (don't raise): the failed-login audit event must commit.
        return unauthorized_response()
    ua = request.headers.get("user-agent")
    issue_session_pair(response, db, user, ip=ip, ua=ua)
    return S.MeResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_platform_admin=user.is_platform_admin,
        tenants=tenant_options(db, user),
    )


@router.post("/refresh", response_model=S.MeResponse)
def refresh(
    request: Request,
    response: Response,
    db: DBSession = Depends(get_db),  # noqa: B008
) -> object:
    settings = get_cached_settings()
    raw = request.cookies.get(cookie_util.REFRESH_COOKIE)
    if not raw or "." not in raw:
        return unauthorized_response("refresh required")
    sid_raw, _, secret = raw.partition(".")
    try:
        sid = uuid.UUID(sid_raw)
    except ValueError:
        return unauthorized_response()
    ip = request.client.host if request.client else None
    try:
        session, new_secret = identity_service.rotate_session(
            db,
            session_id=sid,
            presented_secret=secret,
            ip=ip,
            refresh_days=settings.REFRESH_TOKEN_DAYS,
        )
    except AuthError:
        # Return (don't raise): reuse-detection revocation must commit.
        return unauthorized_response()
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise AuthError("account inactive")
    from app.api.v1._shared import set_session_cookies

    set_session_cookies(response, user_id=user.id, session_id=session.id, secret=new_secret)
    return S.MeResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_platform_admin=user.is_platform_admin,
        tenants=tenant_options(db, user),
    )
