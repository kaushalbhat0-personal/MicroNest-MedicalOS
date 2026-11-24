"""Public invitation acceptance. Single-use expiring tokens; no oracle
(token validity is indistinguishable from expiry).

The invitations table is capability-gated (RLS-exempt by design, see 0005):
the token resolves the tenant server-side, and the accept transaction is
scoped to that tenant before any membership write.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import text
from sqlalchemy.orm import Session as DBSession

from app.api.deps import get_current_user, get_db
from app.api.v1._shared import issue_session_pair, tenant_options
from app.modules.identity import schemas as S
from app.modules.identity.models import User
from app.modules.staff import service as staff_service
from app.modules.tenancy import service as tenancy_service

router = APIRouter(tags=["invites"])


@router.post("/invites/accept", response_model=S.MeResponse)
def accept_invite(
    body: S.InviteAcceptRequest,
    request: Request,
    response: Response,
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.MeResponse:
    from app.api.deps import get_cached_settings
    from app.platform.errors import GoneError
    from app.platform.ratelimit import limiter, normalize_key

    settings = get_cached_settings()
    ip = request.client.host if request.client else "unknown"
    if not limiter.allow(
        scope="invite:ip",
        key=normalize_key(ip),
        limit=settings.LOGIN_IP_LIMIT_PER_MIN,
        window_seconds=60,
    ):
        # No oracle: throttled probes are indistinguishable from bad tokens.
        raise GoneError("invitation invalid or expired")
    tenant_id = tenancy_service.find_invitation_tenant_id(db, token=body.token)
    db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)})
    user, _ = tenancy_service.accept_invitation(
        db, token=body.token, display_name=body.display_name, password=body.password
    )
    client_ip = request.client.host if request.client else None
    issue_session_pair(response, db, user, ip=client_ip, ua=request.headers.get("user-agent"))
    return S.MeResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_platform_admin=user.is_platform_admin,
        email_verified=user.email_verified_at is not None,
        tenants=tenant_options(db, user),
    )


@router.post("/invites/accept-authenticated", response_model=S.MeResponse)
def accept_invite_authenticated(
    body: S.InviteAcceptAuthenticatedRequest,
    request: Request,
    user_session: tuple[User, object] = Depends(get_current_user),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.MeResponse:
    """Accept invite while logged in. Email must match; no password changes."""
    from app.api.deps import get_cached_settings
    from app.platform.errors import GoneError
    from app.platform.ratelimit import limiter, normalize_key

    user, _ = user_session  # type: ignore[misc]
    settings = get_cached_settings()
    if not limiter.allow(
        scope="invite-auth:user",
        key=normalize_key(str(user.id)),
        limit=settings.LOGIN_IP_LIMIT_PER_MIN,
        window_seconds=60,
    ):
        raise GoneError("invitation invalid or expired")
    tenant_id = tenancy_service.find_invitation_tenant_id(db, token=body.token)
    db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)})
    staff_service.accept_invitation_authenticated(db, token=body.token, user=user)
    return S.MeResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_platform_admin=user.is_platform_admin,
        email_verified=user.email_verified_at is not None,
        tenants=tenant_options(db, user),
    )
