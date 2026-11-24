"""SaaS subscription checkout + durable webhook ingress.

Clinic patient billing lives under ``api/v1/billing.py`` and is untouched.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session as DBSession

from app.api.deps import get_db, get_platform_admin, require
from app.api.v1._shared import match_tenant
from app.modules.audit import service as audit_service
from app.modules.identity.models import User
from app.modules.saas_payments import schemas as S
from app.modules.saas_payments import service as pay_svc
from app.modules.subscriptions import schemas as SubS
from app.modules.subscriptions import service as subs_svc
from app.platform.authz.permissions import P
from app.platform.authz.scope import RequestContext
from app.platform.request_context import request_id_ctx

router = APIRouter(tags=["saas-payments"])


@router.post(
    "/tenants/{tenant_id}/subscription/checkout",
    response_model=S.SaasPaymentTransactionResponse,
)
def checkout(
    tenant_id: uuid.UUID,
    body: S.CheckoutRequest,
    ctx: RequestContext = Depends(require(P.SUBSCRIPTION_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.SaasPaymentTransactionResponse:
    match_tenant(ctx, tenant_id)
    payload = pay_svc.initiate_checkout(
        db,
        tenant_id=tenant_id,
        actor_id=ctx.user_id,
        plan_code=body.plan_code,
        idempotency_key=body.idempotency_key,
        is_platform_admin=ctx.is_platform_admin,
        purpose=body.purpose,
    )
    audit_service.append(
        db,
        tenant_id=tenant_id,
        actor_type="user",
        actor_id=str(ctx.user_id),
        action="saas.checkout.initiate",
        resource_type="saas_payment_transaction",
        resource_id=str(payload["id"]),
        request_id=request_id_ctx.get(),
    )
    return S.SaasPaymentTransactionResponse.model_validate(payload)


@router.get(
    "/tenants/{tenant_id}/subscription/payments",
    response_model=list[S.SaasPaymentTransactionResponse],
)
def list_payments(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.SUBSCRIPTION_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    limit: int = 50,
) -> list[S.SaasPaymentTransactionResponse]:
    match_tenant(ctx, tenant_id)
    return [
        S.SaasPaymentTransactionResponse.model_validate(row)
        for row in pay_svc.list_transactions(db, tenant_id=tenant_id, limit=limit)
    ]


@router.post(
    "/tenants/{tenant_id}/subscription/cancel",
    response_model=SubS.SubscriptionDetailResponse,
)
def cancel_subscription(
    tenant_id: uuid.UUID,
    body: S.CancelRequest,
    ctx: RequestContext = Depends(require(P.SUBSCRIPTION_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> SubS.SubscriptionDetailResponse:
    match_tenant(ctx, tenant_id)
    sub = pay_svc.request_cancel(
        db,
        tenant_id=tenant_id,
        actor_id=ctx.user_id,
        reason=body.reason,
        at_period_end=body.at_period_end,
        is_platform_admin=ctx.is_platform_admin,
    )
    return SubS.SubscriptionDetailResponse.model_validate(
        subs_svc.subscription_detail(db, subscription=sub)
    )


@router.post("/webhooks/saas/{provider}")
async def saas_webhook(
    provider: str,
    request: Request,
    db: DBSession = Depends(get_db),  # noqa: B008
    x_razorpay_signature: str | None = Header(default=None, alias="X-Razorpay-Signature"),
    x_saas_signature: str | None = Header(default=None, alias="X-SaaS-Signature"),
) -> dict[str, str]:
    """Provider webhook. Signature required. Receipt is durable after verify."""
    raw = await request.body()
    signature = x_razorpay_signature or x_saas_signature
    result = pay_svc.ingest_webhook(
        db, provider_name=provider, raw_body=raw, signature=signature
    )
    # Always 200 for verified receipts (incl. retryable/permanent) so the
    # provider does not infinite-retry; invalid signatures raise 403.
    out: dict[str, str] = {"status": str(result["status"])}
    if result.get("inbox_id") is not None:
        out["inbox_id"] = str(result["inbox_id"])
    return out


@router.post(
    "/platform/saas/reconcile/{tenant_id}",
    response_model=S.ReconcileResponse,
)
def platform_reconcile(
    tenant_id: uuid.UUID,
    admin: User = Depends(get_platform_admin),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.ReconcileResponse:
    _ = admin
    from sqlalchemy import text

    db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)})
    return S.ReconcileResponse.model_validate(
        pay_svc.reconcile_tenant(db, tenant_id=tenant_id)
    )


@router.get(
    "/platform/saas/webhook-inbox",
    response_model=list[S.WebhookInboxItem],
)
def platform_list_inbox(
    admin: User = Depends(get_platform_admin),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    status: str | None = None,
    limit: int = 50,
) -> list[S.WebhookInboxItem]:
    _ = admin
    return [
        S.WebhookInboxItem.model_validate(row)
        for row in pay_svc.list_inbox(db, status=status, limit=limit)
    ]


@router.post(
    "/platform/saas/webhook-inbox/{inbox_id}/replay",
)
def platform_replay_inbox(
    inbox_id: uuid.UUID,
    admin: User = Depends(get_platform_admin),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> dict[str, str]:
    _ = admin
    result = pay_svc.replay_webhook(db, inbox_id=inbox_id)
    return {"status": str(result["status"]), "inbox_id": str(result.get("inbox_id", inbox_id))}


@router.post(
    "/platform/saas/webhooks/process-due",
    response_model=S.ProcessDueResponse,
)
def platform_process_due(
    admin: User = Depends(get_platform_admin),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    limit: int = 20,
) -> S.ProcessDueResponse:
    _ = admin
    return S.ProcessDueResponse.model_validate(
        pay_svc.process_due_webhooks(db, limit=limit)
    )
