"""Platform administration. Metadata only — NEVER clinical access.
No hidden super-admin bypass exists anywhere in this codebase.

O1.3R adds read-only commercial visibility: a bounded tenant list and a
tenant detail view exposing subscription + specialty metadata. No clinical
records, patient data, staff personal data, credentials, or secrets are
returned; location/membership counts are deferred (they would need their
own RLS review); writes are impossible here by construction (GET only, and
the platform RLS policies are FOR SELECT).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.api.deps import get_db, get_platform_admin
from app.modules.audit import service as audit_service
from app.modules.identity.models import User
from app.modules.subscriptions import service as subscriptions_service
from app.modules.subscriptions.models import Subscription, SubscriptionPlan
from app.modules.tenancy import schemas as S
from app.modules.tenancy import service as tenancy_service
from app.modules.tenancy.models import Tenant
from app.modules.workspaces import service as workspaces_service
from app.modules.workspaces.models import TenantSpecialty
from app.platform.errors import ValidationError
from app.platform.request_context import request_id_ctx

router = APIRouter(prefix="/platform", tags=["platform"])

PLATFORM_TENANT_STATUSES = ("active", "suspended", "deactivated")

# Audit actions for platform reads. Events land in the *viewed* tenant's
# hash chain (refs only, never PII), so each workspace's own audit trail
# records platform access. Success paths only — 401/403/404/422 raise
# before any append, so failures never mint misleading read events.
PLATFORM_TENANT_LIST_ACTION = "platform.tenant.list"
PLATFORM_TENANT_READ_ACTION = "platform.tenant.read"


def _audit_platform_read(
    db: DBSession, *, admin: User, tenant_id: uuid.UUID, action: str
) -> None:
    """Append one platform-read event to the viewed tenant's audit chain.

    RLS is tenant-pinned, so the context is set to the service-verified
    target first (same pattern as `POST /platform/tenants`). The flush is
    immediate and deliberate: ORM autoflush would otherwise defer this
    INSERT until the next query, at which point a list loop may already
    have moved `app.tenant_id` to the next tenant and the row would fail
    WITH CHECK. Call only after the read succeeded.
    """
    from sqlalchemy import text

    db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)})
    audit_service.append(
        db,
        tenant_id=tenant_id,
        actor_type="user",
        actor_id=str(admin.id),
        action=action,
        resource_type="tenant",
        resource_id=str(tenant_id),
        request_id=request_id_ctx.get(),
    )
    db.flush()


class PlatformTenantItem(BaseModel):
    """One workspace's commercial metadata. No clinical, billing, portal,
    staff-personal, credential, or secret fields exist on this shape."""

    id: uuid.UUID
    name: str
    slug: str
    status: str
    created_at: datetime
    updated_at: datetime
    subscription: S.SubscriptionSummary | None = None
    specialties_enabled: list[str] = []
    specialties: list[S.SpecialtyDetail] = []


class PlatformTenantList(BaseModel):
    items: list[PlatformTenantItem] = Field(default_factory=list)
    total: int
    limit: int
    offset: int


def _build_item(
    tenant: Tenant,
    subscription: Subscription | None,
    plans: dict[object, SubscriptionPlan],
    specialty_rows: list[TenantSpecialty],
) -> PlatformTenantItem:
    summary = None
    if subscription is not None:
        summary = subscriptions_service.build_summary(
            subscription, plans.get(subscription.plan_id)
        )
    details = workspaces_service.specialty_details_for_rows(specialty_rows)
    return PlatformTenantItem(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        status=tenant.status,
        created_at=tenant.created_at,
        updated_at=tenant.updated_at,
        subscription=summary,
        specialties_enabled=[str(d["code"]) for d in details],
        specialties=[
            S.SpecialtyDetail(
                code=str(d["code"]),
                pack_version=str(d["pack_version"]),
                label=str(d["label"]),
                maturity=str(d["maturity"]),
                ready_for_use=bool(d["ready_for_use"]),
            )
            for d in details
        ],
    )


@router.get("/health")
def health(
    _admin: User = Depends(get_platform_admin),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> dict[str, str]:
    from sqlalchemy import text

    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.post("/tenants", response_model=S.TenantResponse)
def create_tenant(
    body: S.TenantCreateRequest,
    admin: User = Depends(get_platform_admin),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.TenantResponse:
    from sqlalchemy import text

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


@router.get("/tenants", response_model=PlatformTenantList)
def list_tenants(
    admin: User = Depends(get_platform_admin),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
) -> PlatformTenantList:
    """Bounded, read-only workspace list for platform operators.

    Auth: existing platform-admin flag only (never tenant membership,
    headers, or body). Pagination is bounded (limit 1..100). Only the
    commercial metadata shaped in PlatformTenantItem is returned.
    Each returned workspace records one `platform.tenant.list` event in
    its own audit chain (success path only).
    """
    if status is not None and status not in PLATFORM_TENANT_STATUSES:
        raise ValidationError(f"unknown tenant status: {status!r}")
    base = select(Tenant)
    if status is not None:
        base = base.where(Tenant.status == status)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = (
        db.execute(
            base.order_by(Tenant.created_at.asc(), Tenant.id.asc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    tenant_ids = [t.id for t in rows]
    subs = subscriptions_service.subscriptions_for_tenants(db, tenant_ids=tenant_ids)
    plans = subscriptions_service.plans_by_ids(
        db, plan_ids=[s.plan_id for s in subs.values()]
    )
    spec_rows = workspaces_service.specialty_rows_for_tenants(
        db, tenant_ids=tenant_ids
    )
    items = [
        _build_item(t, subs.get(t.id), plans, spec_rows.get(t.id, [])) for t in rows
    ]
    for item in items:
        _audit_platform_read(
            db, admin=admin, tenant_id=item.id, action=PLATFORM_TENANT_LIST_ACTION
        )
    return PlatformTenantList(
        items=items,
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.get("/tenants/{tenant_id}", response_model=PlatformTenantItem)
def get_platform_tenant(
    tenant_id: uuid.UUID,
    admin: User = Depends(get_platform_admin),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> PlatformTenantItem:
    """Read-only commercial detail for one workspace.

    The tenant id is a lookup key, not proof of access: only platform
    admins reach this code path. Unknown ids are 404 (no audit event —
    there is no chain to record it in). Success records one
    `platform.tenant.read` event in the target's chain.
    """
    tenant = tenancy_service.get_tenant(db, tenant_id)
    sub = subscriptions_service.get_subscription(db, tenant_id=tenant.id)
    plans: dict[object, SubscriptionPlan] = {}
    if sub is not None:
        plans = subscriptions_service.plans_by_ids(db, plan_ids=[sub.plan_id])
    rows = workspaces_service.get_tenant_specialty_rows(db, tenant=tenant)
    item = _build_item(tenant, sub, plans, rows)
    _audit_platform_read(
        db, admin=admin, tenant_id=tenant.id, action=PLATFORM_TENANT_READ_ACTION
    )
    return item
