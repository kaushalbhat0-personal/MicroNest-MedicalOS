"""Platform administration. Metadata only — NEVER clinical access.
No hidden super-admin bypass exists anywhere in this codebase.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session as DBSession

from app.api.deps import get_db, get_platform_admin
from app.modules.audit import service as audit_service
from app.modules.identity.models import User
from app.modules.tenancy import schemas as S
from app.modules.tenancy import service as tenancy_service
from app.platform.request_context import request_id_ctx

router = APIRouter(prefix="/platform", tags=["platform"])


@router.get("/health")
def health(
    _admin: User = Depends(get_platform_admin),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.post("/tenants", response_model=S.TenantResponse)
def create_tenant(
    body: S.TenantCreateRequest,
    admin: User = Depends(get_platform_admin),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.TenantResponse:
    t = tenancy_service.create_tenant(db, name=body.name, slug=body.slug)
    # RLS context for this single, service-verified tenant (never client input).
    db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(t.id)})
    audit_service.append(
        db,
        tenant_id=t.id,
        actor_type="user",
        actor_id=str(admin.id),
        action="tenant.create",
        resource_type="tenant",
        resource_id=str(t.id),
        request_id=request_id_ctx.get(),
    )
    return S.TenantResponse(id=t.id, name=t.name, slug=t.slug, status=t.status)
