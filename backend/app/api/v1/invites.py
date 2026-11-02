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

from app.api.deps import get_db
from app.api.v1._shared import issue_session_pair, tenant_options
from app.modules.identity import schemas as S
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
    from app.platform.ratelimit import limiter

    settings = get_cached_settings()
    ip = request.client.host if request.client else "unknown"
    if not limiter.allow(
        scope="invite:ip",
        key=ip,
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
        tenants=tenant_options(db, user),
    )
