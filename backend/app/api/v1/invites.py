"""Public invitation acceptance. Single-use expiring tokens; no oracle
(token validity is indistinguishable from expiry)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session as DBSession

from app.api.deps import get_db
from app.api.v1._shared import tenant_options
from app.api.v1.auth import _issue_pair
from app.modules.identity import schemas as S
from app.modules.tenancy import service as tenancy_service

router = APIRouter(tags=["invites"])


@router.post("/invites/accept", response_model=S.MeResponse)
def accept_invite(
    body: S.InviteAcceptRequest, request: Request, response: Response,
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.MeResponse:
    user, _ = tenancy_service.accept_invitation(
        db, token=body.token, display_name=body.display_name, password=body.password
    )
    ip = request.client.host if request.client else None
    _issue_pair(response, db, user, ip=ip, ua=request.headers.get("user-agent"))
    return S.MeResponse(
        id=user.id, email=user.email, display_name=user.display_name,
        is_platform_admin=user.is_platform_admin,
        tenants=tenant_options(db, user),
    )
