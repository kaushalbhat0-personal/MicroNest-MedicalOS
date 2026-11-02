"""API dependencies: settings, sessions, auth, tenant resolution, permission
gates. This is the ONLY place tenant scope is derived — endpoints receive a
resolved RequestContext and never touch raw tenant inputs.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from functools import lru_cache

import jwt
from fastapi import Cookie, Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.orm import Session as DBSession

from app.modules.identity.models import Session as SessionRow
from app.modules.identity.models import User
from app.modules.tenancy import service as tenancy_service
from app.modules.tenancy.models import Membership, Role
from app.platform import db as dbmod
from app.platform.authz.permissions import PLATFORM_ONLY
from app.platform.authz.scope import RequestContext
from app.platform.config import Settings, get_settings
from app.platform.errors import AuthError, ForbiddenError
from app.platform.request_context import request_id_ctx
from app.platform.security import cookies as cookie_util
from app.platform.security import tokens as token_util
from app.platform.time import UTC

bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache
def get_cached_settings() -> Settings:
    return get_settings()


_factory = None


def get_factory() -> dbmod.sessionmaker[DBSession]:
    global _factory
    if _factory is None:
        settings = get_cached_settings()
        if not settings.APP_DATABASE_URL:
            raise RuntimeError("APP_DATABASE_URL is not configured")
        _factory = dbmod.make_session_factory(settings.APP_DATABASE_URL)
    return _factory


def get_db():  # type: ignore[no-untyped-def]
    factory = get_factory()
    with dbmod.scoped_transaction(factory) as session:
        yield session


def _bearer_token(
    creds: HTTPAuthorizationCredentials | None,
) -> str | None:
    if creds is not None and creds.scheme.lower() == "bearer" and creds.credentials:
        return creds.credentials
    return None


def _read_access_token(
    request: Request,
    hos_access: str | None,
    creds: HTTPAuthorizationCredentials | None,
) -> str:
    token = _bearer_token(creds)
    if token:
        return token
    cookie_val = request.cookies.get(cookie_util.ACCESS_COOKIE, hos_access)
    if cookie_val:
        return cookie_val
    raise AuthError("authentication required")


def get_current_user(
    request: Request,
    db: DBSession = Depends(get_db),  # noqa: B008
    hos_access: str | None = Cookie(default=None),
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),  # noqa: B008
) -> tuple[User, SessionRow]:
    settings = get_cached_settings()
    raw = _read_access_token(request, hos_access, creds)
    try:
        claims = token_util.decode_access_token(
            raw, secret=settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
    except jwt.PyJWTError as exc:
        raise AuthError("invalid or expired token") from exc
    try:
        user_id = uuid.UUID(str(claims["sub"]))
        session_id = uuid.UUID(str(claims["sid"]))
    except (KeyError, ValueError) as exc:
        raise AuthError("invalid token claims") from exc
    row = db.get(SessionRow, session_id)
    if row is None or row.user_id != user_id or row.revoked_at is not None:
        raise AuthError("session revoked")
    if row.expires_at <= datetime.now(UTC):
        raise AuthError("session expired")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthError("account inactive")
    # Actor attribution for RLS: membership reads are allowed for the
    # authenticated user (tenant writes still need app.tenant_id, set later
    # by get_ctx after the tenant selector is validated).
    db.execute(text("SELECT set_config('app.user_id', :a, true)"), {"a": str(user.id)})
    dbmod.actor_ctx.set(str(user.id))
    return user, row


def get_ctx(
    request: Request,
    user_session: tuple[User, SessionRow] = Depends(get_current_user),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    x_tenant: str | None = Header(default=None, alias="X-Tenant"),
) -> RequestContext:
    """Resolve tenant scope server-side. X-Tenant is a selector only."""
    user, _ = user_session
    memberships = tenancy_service.user_memberships(db, user.id)
    if not memberships:
        raise ForbiddenError("no tenant membership")
    selected: Membership | None = None
    if x_tenant:
        try:
            wanted = uuid.UUID(x_tenant)
        except ValueError as exc:
            raise ForbiddenError("unknown tenant") from exc
        for m in memberships:
            if m.tenant_id == wanted:
                selected = m
                break
        if selected is None:
            # Indistinguishable from "not found": do not confirm existence.
            raise ForbiddenError("unknown tenant")
    elif len(memberships) == 1:
        selected = memberships[0]
    else:
        raise ForbiddenError("tenant selection required")
    tenant = tenancy_service.get_tenant(db, selected.tenant_id)
    if tenant.status != "active":
        raise ForbiddenError("tenant is not active")
    # Tenant context BEFORE any tenant-scoped read (RLS fail-closed default).
    db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant.id)})
    role = db.get(Role, selected.role_id)
    if role is None:
        raise ForbiddenError("role revoked")
    loc_ids = tenancy_service.membership_location_ids(db, selected.id)
    # Apply RLS context to THIS transaction (SET LOCAL is txn-scoped).
    db.execute(text("SELECT set_config('app.actor_id', :a, true)"), {"a": str(user.id)})
    dbmod.tenant_ctx.set(str(tenant.id))
    dbmod.actor_ctx.set(str(user.id))
    return RequestContext(
        user_id=user.id,
        session_id=user_session[1].id,
        tenant_id=tenant.id,
        membership_id=selected.id,
        role=role.name,
        permissions=frozenset(role.permissions or []),
        location_ids=frozenset(loc_ids),
        is_platform_admin=bool(user.is_platform_admin),
        request_id=request_id_ctx.get(),
    )


def get_platform_admin(
    user_session: tuple[User, SessionRow] = Depends(get_current_user),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> User:
    """Platform scope: user flag only, no tenant. Caller manages RLS
    explicitly for any tenant-scoped write (service-verified IDs only)."""
    user, _ = user_session
    if not user.is_platform_admin:
        raise ForbiddenError("platform permission required")
    dbmod.actor_ctx.set(str(user.id))
    return user


def require(permission: str):  # type: ignore[no-untyped-def]
    def _check(ctx: RequestContext = Depends(get_ctx)) -> RequestContext:  # noqa: B008
        if permission in PLATFORM_ONLY and not ctx.is_platform_admin:
            raise ForbiddenError("platform permission required")
        if permission not in ctx.permissions and not (
            permission in PLATFORM_ONLY and ctx.is_platform_admin
        ):
            raise ForbiddenError("permission denied")
        return ctx

    return _check
