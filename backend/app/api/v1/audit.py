"""Audit reads. Scoped to the caller's tenant. Reading audit is itself
audited (single entry, resource=audit stream of the tenant)."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.api.deps import get_ctx, get_db, require
from app.modules.audit import schemas as S
from app.modules.audit import service as audit_service
from app.modules.audit.models import AuditEvent
from app.platform.authz.permissions import P
from app.platform.authz.scope import RequestContext
from app.platform.errors import NotFoundError
from app.platform.request_context import request_id_ctx

router = APIRouter(tags=["audit"])


@router.get("/tenants/{tenant_id}/audit", response_model=list[S.AuditEventResponse])
def read_audit(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.AUDIT_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    since: datetime | None = Query(default=None),
    limit: int = Query(default=50, le=200),
) -> list[S.AuditEventResponse]:
    if tenant_id != ctx.tenant_id:
        raise NotFoundError("not found")
    q = (
        select(AuditEvent)
        .where(AuditEvent.tenant_id == tenant_id)
        .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
        .limit(limit)
    )
    if since is not None:
        q = q.where(AuditEvent.occurred_at >= since)
    rows = db.execute(q).scalars().all()
    audit_service.append(
        db, tenant_id=tenant_id, actor_type="user", actor_id=str(ctx.user_id),
        action="audit.read", resource_type="audit", resource_id=str(tenant_id),
        request_id=request_id_ctx.get(),
    )
    return [
        S.AuditEventResponse(
            id=r.id, occurred_at=r.occurred_at, tenant_id=r.tenant_id,
            actor_type=r.actor_type, actor_id=r.actor_id, action=r.action,
            resource_type=r.resource_type, resource_id=r.resource_id,
            request_id=r.request_id, result=r.result,
        )
        for r in rows
    ]
