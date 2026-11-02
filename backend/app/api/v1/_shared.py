"""Shared API helpers (kept minimal; domain logic lives in services)."""

import uuid

from fastapi import Response
from sqlalchemy.orm import Session as DBSession

from app.modules.identity import schemas as S
from app.modules.identity.models import User
from app.modules.tenancy import service as tenancy_service
from app.platform.authz.scope import RequestContext
from app.platform.errors import NotFoundError
from app.platform.logging_setup import get_logger

log = get_logger(__name__)


def tenant_options(db: DBSession, user: User) -> list[S.TenantOption]:
    out = []
    for m in tenancy_service.user_memberships(db, user.id):
        try:
            t = tenancy_service.get_tenant(db, m.tenant_id)
        except Exception as exc:  # noqa: BLE001 - skip dangling, never fail the request
            log.debug("skipping dangling membership: %s", exc)
            continue
        out.append(S.TenantOption(id=t.id, slug=t.slug, name=t.name))
    return out


def match_tenant(ctx: RequestContext, tenant_id: uuid.UUID) -> None:
    """Path-tenant must equal the resolved tenant. Mismatch is 404, never a
    403-oracle (a cross-tenant probe learns nothing). Single implementation."""
    if tenant_id != ctx.tenant_id:
        raise NotFoundError("not found")


def set_session_cookies(
    response: Response, *, user_id: object, session_id: object, secret: str
) -> None:
    """Set auth cookies for an existing session+secret pair. Single place
    where cookie names/paths/scopes are decided (login, refresh, accept)."""
    import uuid as _uuid

    from app.api.deps import get_cached_settings
    from app.platform.security import cookies as cookie_util
    from app.platform.security import tokens as token_util

    settings = get_cached_settings()
    access = token_util.create_access_token(
        user_id=_uuid.UUID(str(user_id)),
        session_id=_uuid.UUID(str(session_id)),
        secret=settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
        minutes=settings.ACCESS_TOKEN_MINUTES,
    )
    cookie_util.set_auth_cookies(
        response,
        access=access,
        refresh=f"{session_id}.{secret}",
        secure=settings.COOKIE_SECURE,
        domain=settings.COOKIE_DOMAIN,
        refresh_days=settings.REFRESH_TOKEN_DAYS,
    )


def issue_session_pair(
    response: Response, db: DBSession, user: User, *, ip: str | None, ua: str | None
) -> object:
    """Create a session + set auth cookies. Returns the session row."""
    from app.api.deps import get_cached_settings
    from app.modules.identity import service as identity_service

    settings = get_cached_settings()
    session, refresh_secret = identity_service.create_session(
        db, user, ip=ip, user_agent=ua, refresh_days=settings.REFRESH_TOKEN_DAYS
    )
    set_session_cookies(response, user_id=user.id, session_id=session.id, secret=refresh_secret)
    return session
