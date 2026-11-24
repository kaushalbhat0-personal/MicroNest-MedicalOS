"""P2.0 commercial plan catalog + tenant subscription APIs.

No payment provider. Limits are informational. Tenant ownership is derived
from server context (X-Tenant) or platform admin path — never from client body.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session as DBSession

from app.api.deps import (
    RequestContext,
    get_current_user,
    get_db,
    get_platform_admin,
    require,
)
from app.api.v1._shared import match_tenant
from app.modules.audit import service as audit_service
from app.modules.identity.models import User
from app.modules.subscriptions import entitlements as ent_svc
from app.modules.subscriptions import schemas as S
from app.modules.subscriptions import service as subs_svc
from app.modules.subscriptions.models import SubscriptionEvent
from app.modules.tenancy import service as tenancy_service
from app.platform.authz.permissions import P
from app.platform.request_context import request_id_ctx

router = APIRouter(tags=["subscriptions"])


def _event_resp(ev: SubscriptionEvent) -> S.SubscriptionEventResponse:
    return S.SubscriptionEventResponse(
        id=ev.id,
        event_type=ev.event_type,
        from_status=ev.from_status,
        to_status=ev.to_status,
        from_plan_id=ev.from_plan_id,
        to_plan_id=ev.to_plan_id,
        actor_id=ev.actor_id,
        note=ev.note,
        created_at=ev.created_at,
    )


@router.get("/plans", response_model=list[S.PlanResponse])
def list_plans(
    db: DBSession = Depends(get_db),  # noqa: B008
    user_session: tuple[User, object] = Depends(get_current_user),  # noqa: B008
) -> list[S.PlanResponse]:
    """Authenticated catalog of active plan families (latest version each).

    Requires a login session. Catalog is not patient-administered; portal-only
    users can call this but UI does not surface it. No payment claims.
    """
    _user, _ = user_session
    return [
        S.PlanResponse.model_validate(subs_svc.plan_to_dict(p))
        for p in subs_svc.list_active_plans(db)
    ]


@router.get("/plans/{code}", response_model=S.PlanResponse)
def get_plan(
    code: str,
    db: DBSession = Depends(get_db),  # noqa: B008
    user_session: tuple[User, object] = Depends(get_current_user),  # noqa: B008
) -> S.PlanResponse:
    _user, _ = user_session
    plan = subs_svc.get_plan_by_code(db, code=code)
    return S.PlanResponse.model_validate(subs_svc.plan_to_dict(plan))


@router.get(
    "/tenants/{tenant_id}/subscription",
    response_model=S.SubscriptionDetailResponse,
)
def get_tenant_subscription(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.SUBSCRIPTION_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.SubscriptionDetailResponse:
    match_tenant(ctx, tenant_id)
    sub = subs_svc.require_subscription(db, tenant_id=tenant_id)
    return S.SubscriptionDetailResponse.model_validate(
        subs_svc.subscription_detail(db, subscription=sub)
    )


@router.get(
    "/tenants/{tenant_id}/subscription/events",
    response_model=list[S.SubscriptionEventResponse],
)
def get_tenant_subscription_events(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.SUBSCRIPTION_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    limit: int = 100,
) -> list[S.SubscriptionEventResponse]:
    match_tenant(ctx, tenant_id)
    return [_event_resp(e) for e in subs_svc.list_events(db, tenant_id=tenant_id, limit=limit)]


@router.get(
    "/tenants/{tenant_id}/entitlements",
    response_model=S.EntitlementSummaryResponse,
)
def get_tenant_entitlements(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.SUBSCRIPTION_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.EntitlementSummaryResponse:
    """Shadow entitlement summary. Never enforces; never mutates."""
    match_tenant(ctx, tenant_id)
    payload = ent_svc.resolve_entitlements(db, tenant_id=tenant_id)
    return S.EntitlementSummaryResponse.model_validate(payload)


@router.post(
    "/tenants/{tenant_id}/subscription/assign-plan",
    response_model=S.SubscriptionDetailResponse,
)
def assign_plan(
    tenant_id: uuid.UUID,
    body: S.AssignPlanRequest,
    admin: User = Depends(get_platform_admin),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.SubscriptionDetailResponse:
    """Platform-admin plan assignment. No payment; catalog-only."""
    tenancy_service.get_tenant(db, tenant_id)
    db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)})
    db.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(admin.id)})
    sub = subs_svc.assign_plan(
        db,
        tenant_id=tenant_id,
        actor_id=admin.id,
        plan_code=body.plan_code,
        note=body.note,
        target_status=body.target_status,
    )
    audit_service.append(
        db,
        tenant_id=tenant_id,
        actor_type="user",
        actor_id=str(admin.id),
        action="subscription.plan.assign",
        resource_type="subscription",
        resource_id=str(sub.id),
        request_id=request_id_ctx.get(),
    )
    return S.SubscriptionDetailResponse.model_validate(
        subs_svc.subscription_detail(db, subscription=sub)
    )


@router.post(
    "/tenants/{tenant_id}/subscription/transition",
    response_model=S.SubscriptionDetailResponse,
)
def transition_subscription(
    tenant_id: uuid.UUID,
    body: S.TransitionStatusRequest,
    admin: User = Depends(get_platform_admin),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.SubscriptionDetailResponse:
    """Platform-admin status transition. Never mutates tenants.status."""
    tenant_before = tenancy_service.get_tenant(db, tenant_id)
    status_before = tenant_before.status
    db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)})
    db.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(admin.id)})
    sub = subs_svc.transition_status(
        db,
        tenant_id=tenant_id,
        actor_id=admin.id,
        new_status=body.status,
        note=body.note,
        cancel_reason=body.cancel_reason,
        grace_ends_at=body.grace_ends_at,
    )
    audit_service.append(
        db,
        tenant_id=tenant_id,
        actor_type="user",
        actor_id=str(admin.id),
        action="subscription.status.transition",
        resource_type="subscription",
        resource_id=str(sub.id),
        request_id=request_id_ctx.get(),
    )
    tenant_after = tenancy_service.get_tenant(db, tenant_id)
    assert tenant_after.status == status_before  # abuse axis untouched
    return S.SubscriptionDetailResponse.model_validate(
        subs_svc.subscription_detail(db, subscription=sub)
    )


@router.post(
    "/tenants/{tenant_id}/subscription/extend-trial",
    response_model=S.SubscriptionDetailResponse,
)
def extend_trial(
    tenant_id: uuid.UUID,
    body: S.ExtendTrialRequest,
    admin: User = Depends(get_platform_admin),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.SubscriptionDetailResponse:
    tenancy_service.get_tenant(db, tenant_id)
    db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)})
    db.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(admin.id)})
    sub = subs_svc.extend_trial(
        db,
        tenant_id=tenant_id,
        actor_id=admin.id,
        days=body.days,
        note=body.note,
    )
    audit_service.append(
        db,
        tenant_id=tenant_id,
        actor_type="user",
        actor_id=str(admin.id),
        action="subscription.trial.extend",
        resource_type="subscription",
        resource_id=str(sub.id),
        request_id=request_id_ctx.get(),
    )
    return S.SubscriptionDetailResponse.model_validate(
        subs_svc.subscription_detail(db, subscription=sub)
    )
