"""Self-service workspace provisioning (O1.2a).

`POST /api/v1/workspaces` — atomic, authenticated, X-Tenant-less (this
operation CREATES the tenant). The requesting user is derived exclusively
from the authenticated server-side identity; the body carries no owner ids.

- Requires an `Idempotency-Key` header (UUIDv4 shape; missing/malformed
  is 422). Same key + same request replays the original 201; same key +
  different request is 409.
- No verified-email precondition: unverified users provision normally.
- `X-Tenant` is neither required nor read here.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session as DBSession

from app.api import errors as error_handlers
from app.api.deps import get_current_user, get_db
from app.modules.identity.models import Session as SessionRow
from app.modules.identity.models import User
from app.modules.workspaces import schemas as W
from app.modules.workspaces import service as workspaces_service
from app.platform.errors import ValidationError

router = APIRouter(tags=["workspaces"])


def _require_idempotency_key(raw: str | None) -> str:
    if not raw or not raw.strip():
        raise ValidationError("Idempotency-Key header is required")
    try:
        return str(uuid.UUID(raw.strip()))
    except ValueError as exc:
        raise ValidationError("Idempotency-Key must be a UUID") from exc


@router.post(
    "/workspaces",
    response_model=W.WorkspaceResponse,
    status_code=201,
    responses=error_handlers.AUTHZ_RESPONSES,
)
def create_workspace(
    body: W.WorkspaceCreateRequest,
    user_session: tuple[User, SessionRow] = Depends(get_current_user),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> W.WorkspaceResponse:
    user, _ = user_session
    key = _require_idempotency_key(idempotency_key)
    return workspaces_service.provision_workspace(db, user=user, body=body, idempotency_key=key)
