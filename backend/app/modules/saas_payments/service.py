"""SaaS checkout, durable webhook inbox, reconciliation.

Subscription mutations go through ``subscriptions.service`` only.
Browser return URLs never activate subscriptions.
Verified webhook receipts survive transient processing failures (P2.5).
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session as DBSession

from app.modules.saas_payments import models as M
from app.modules.saas_payments.provider import (
    NormalizedProviderEvent,
    get_provider,
)
from app.modules.subscriptions import service as subs_svc
from app.modules.subscriptions.models import Subscription, SubscriptionPlan
from app.modules.tenancy.models import TenantOwner
from app.platform import ids
from app.platform.config import get_settings
from app.platform.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.platform.events.outbox import backoff_for_attempt
from app.platform.time import now as utcnow

log = logging.getLogger("healthcare_os.saas_payments")

# Permanent business errors — do not retry indefinitely.
_PERMANENT_CODES = frozenset({"conflict", "validation_failed", "not_found", "forbidden"})


def _grace_days() -> int:
    settings = get_settings()
    return int(getattr(settings, "SAAS_GRACE_DAYS", 7) or 7)


def _max_attempts() -> int:
    settings = get_settings()
    return int(getattr(settings, "SAAS_WEBHOOK_MAX_ATTEMPTS", M.WEBHOOK_MAX_ATTEMPTS) or 8)


def _safe_err(exc: BaseException) -> str:
    """Redact exception text for storage/logs — no secrets/PHI."""
    name = type(exc).__name__
    msg = str(exc)[:200]
    for needle in ("key_secret", "webhook_secret", "Authorization", "rzp_test_", "rzp_live_"):
        if needle.lower() in msg.lower():
            return name
    return f"{name}:{msg}"


def assert_checkout_actor(
    db: DBSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, is_platform_admin: bool
) -> None:
    if is_platform_admin:
        return
    owner = db.execute(
        select(TenantOwner).where(
            TenantOwner.tenant_id == tenant_id, TenantOwner.user_id == user_id
        )
    ).scalar_one_or_none()
    if owner is not None:
        return
    from app.modules.tenancy.models import Membership, Role
    from app.platform.authz.permissions import P

    row = db.execute(
        select(Membership, Role)
        .join(Role, Role.id == Membership.role_id)
        .where(
            Membership.tenant_id == tenant_id,
            Membership.user_id == user_id,
            Membership.is_active.is_(True),
        )
    ).first()
    if row is None:
        raise ForbiddenError("not a member of this tenant")
    _m, role = row
    if P.STAFF_MANAGE in set(role.permissions or []) or role.name == "tenant_admin":
        return
    raise ForbiddenError("checkout requires tenant owner or tenant admin")


def _paid_plan(db: DBSession, *, plan_code: str) -> SubscriptionPlan:
    plan = subs_svc.get_plan_by_code(db, code=plan_code)
    if not plan.is_active:
        raise ValidationError("plan revision is not active in catalog")
    if plan.price_minor <= 0 or plan.billing_interval is None:
        raise ValidationError("plan is not a paid catalog revision")
    if plan.currency != "INR":
        raise ValidationError("only INR catalog plans are supported")
    return plan


def _event_refs(event: NormalizedProviderEvent) -> dict[str, Any]:
    return {
        "event_type": event.event_type,
        "order_id": event.provider_order_id,
        "payment_id": event.provider_payment_id,
        "amount_minor": event.amount_minor,
        "currency": event.currency,
        "refund_amount_minor": event.refund_amount_minor,
    }


def initiate_checkout(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    plan_code: str,
    idempotency_key: str,
    is_platform_admin: bool = False,
    purpose: str = "checkout",
) -> dict[str, Any]:
    """Create (or replay) a pending SaaS payment transaction + provider order."""
    assert_checkout_actor(
        db,
        tenant_id=tenant_id,
        user_id=actor_id,
        is_platform_admin=is_platform_admin,
    )
    key = (idempotency_key or "").strip()
    if len(key) < 8 or len(key) > 128:
        raise ValidationError("idempotency_key must be 8-128 characters")
    if purpose not in ("checkout", "renewal"):
        raise ValidationError("purpose must be checkout or renewal")

    existing = db.execute(
        select(M.SaasPaymentTransaction).where(
            M.SaasPaymentTransaction.tenant_id == tenant_id,
            M.SaasPaymentTransaction.idempotency_key == key,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return _txn_public(db, existing)

    plan = _paid_plan(db, plan_code=plan_code)
    sub = subs_svc.require_subscription(db, tenant_id=tenant_id)
    if purpose == "renewal" and sub.status == "cancelled":
        raise ConflictError("cannot renew a cancelled subscription; reactivate first")
    provider = get_provider()
    provider.assert_environment()
    now = utcnow()

    cust = db.execute(
        select(M.SaasCustomer).where(
            M.SaasCustomer.tenant_id == tenant_id,
            M.SaasCustomer.provider == provider.name,
        )
    ).scalar_one_or_none()
    if cust is None:
        cust = M.SaasCustomer(
            id=ids.uuid7(),
            tenant_id=tenant_id,
            provider=provider.name,
            provider_customer_id=provider.create_customer(
                tenant_id=tenant_id, email=None
            ),
            created_at=now,
            updated_at=now,
        )
        db.add(cust)
        db.flush()

    txn_id = ids.uuid7()
    receipt = f"saas_{txn_id.hex[:20]}"
    order = provider.create_order(
        amount_minor=plan.price_minor,
        currency=plan.currency,
        receipt=receipt,
        notes={
            "tenant_id": str(tenant_id),
            "transaction_id": str(txn_id),
            "plan_code": plan.code,
            "purpose": purpose,
        },
    )
    if order.amount_minor != plan.price_minor or order.currency.upper() != plan.currency:
        raise ConflictError("provider order amount/currency mismatch")

    period_start = now
    if purpose == "renewal" and sub.period_end and sub.period_end > now:
        period_start = sub.period_end
    if plan.billing_interval == "year":
        period_end = period_start + timedelta(days=365)
    else:
        period_end = period_start + timedelta(days=30)

    txn = M.SaasPaymentTransaction(
        id=txn_id,
        tenant_id=tenant_id,
        subscription_id=sub.id,
        plan_id=plan.id,
        provider=provider.name,
        status=M.TXN_PENDING,
        amount_minor=plan.price_minor,
        currency=plan.currency,
        billing_interval=plan.billing_interval,
        provider_order_id=order.order_id,
        provider_payment_id=None,
        idempotency_key=key,
        purpose=purpose,
        period_start=period_start,
        period_end=period_end,
        paid_at=None,
        failure_reason=None,
        refunded_amount_minor=0,
        created_by=actor_id,
        created_at=now,
        updated_at=now,
    )
    db.add(txn)
    db.flush()
    if not sub.provider_ref:
        sub.provider_ref = cust.provider_customer_id
        sub.updated_at = now
    log.info(
        "saas_checkout_created tenant_id=%s txn_id=%s plan=%s amount=%s provider=%s purpose=%s",
        str(tenant_id),
        str(txn.id),
        plan.code,
        plan.price_minor,
        provider.name,
        purpose,
    )
    out = _txn_public(db, txn)
    out["checkout"] = {
        "provider": order.provider,
        "order_id": order.order_id,
        "amount_minor": order.amount_minor,
        "currency": order.currency,
        "public_key": order.public_key,
        "hint": order.checkout_hint,
        "return_url_informational": True,
    }
    return out


def _txn_public(db: DBSession, txn: M.SaasPaymentTransaction) -> dict[str, Any]:
    plan = db.get(SubscriptionPlan, txn.plan_id)
    return {
        "id": txn.id,
        "tenant_id": txn.tenant_id,
        "status": txn.status,
        "amount_minor": txn.amount_minor,
        "currency": txn.currency,
        "billing_interval": txn.billing_interval,
        "plan_code": plan.code if plan else None,
        "plan_name": plan.name if plan else None,
        "provider": txn.provider,
        "provider_order_id": txn.provider_order_id,
        "paid_at": txn.paid_at,
        "period_start": txn.period_start,
        "period_end": txn.period_end,
        "idempotency_key": txn.idempotency_key,
        "purpose": txn.purpose,
        "refunded_amount_minor": txn.refunded_amount_minor,
        "created_at": txn.created_at,
        "failure_reason": txn.failure_reason,
    }


def list_transactions(
    db: DBSession, *, tenant_id: uuid.UUID, limit: int = 50
) -> list[dict[str, Any]]:
    capped = min(max(limit, 1), 100)
    rows = (
        db.execute(
            select(M.SaasPaymentTransaction)
            .where(M.SaasPaymentTransaction.tenant_id == tenant_id)
            .order_by(
                M.SaasPaymentTransaction.created_at.desc(),
                M.SaasPaymentTransaction.id.desc(),
            )
            .limit(capped)
        )
        .scalars()
        .all()
    )
    return [_txn_public(db, r) for r in rows]


def ingest_webhook(
    db: DBSession,
    *,
    provider_name: str,
    raw_body: bytes,
    signature: str | None,
) -> dict[str, Any]:
    """Verify signature, persist durable receipt, process once.

    Invalid signatures are rejected without storing a valid event.
    After a verified receipt is persisted, processing failures do not
    discard the event — they mark retryable/permanent failure and return
    accepted so the provider can stop hammering.
    """
    provider = get_provider()
    if provider.name != provider_name:
        raise ValidationError("provider mismatch")
    provider.assert_environment()
    # 1) Signature — fail closed, never store as verified.
    provider.verify_webhook(raw_body=raw_body, signature=signature)
    event = provider.parse_webhook(raw_body=raw_body)
    now = utcnow()

    existing = db.execute(
        select(M.SaasWebhookInbox)
        .where(
            M.SaasWebhookInbox.provider == event.provider,
            M.SaasWebhookInbox.provider_event_id == event.event_id,
        )
        .with_for_update()
    ).scalar_one_or_none()

    if existing is not None:
        if existing.status == M.INBOX_PROCESSED:
            return {"status": "duplicate", "inbox_id": str(existing.id)}
        if existing.status == M.INBOX_DUPLICATE:
            return {"status": "duplicate", "inbox_id": str(existing.id)}
        inbox = existing
        # Redelivery while still open — keep durable row, re-queue.
        inbox.status = M.INBOX_PENDING
        inbox.next_attempt_at = now
        inbox.last_error = None
        inbox.event_refs = _event_refs(event)
    else:
        inbox = M.SaasWebhookInbox(
            id=ids.uuid7(),
            provider=event.provider,
            provider_event_id=event.event_id,
            event_type=event.event_type,
            status=M.INBOX_PENDING,
            payload_digest=event.raw_digest,
            event_refs=_event_refs(event),
            related_transaction_id=None,
            tenant_id=None,
            attempts=0,
            last_error=None,
            next_attempt_at=now,
            locked_until=None,
            received_at=now,
            processed_at=None,
        )
        db.add(inbox)
        db.flush()

    # 2) Process immediately (same request). Failures stay durable.
    result = _process_inbox_row(db, inbox=inbox, event=event)
    return result


def _process_inbox_row(
    db: DBSession,
    *,
    inbox: M.SaasWebhookInbox,
    event: NormalizedProviderEvent | None = None,
) -> dict[str, Any]:
    now = utcnow()
    if inbox.status == M.INBOX_PROCESSED:
        return {"status": "duplicate", "inbox_id": str(inbox.id)}

    max_att = _max_attempts()
    inbox.status = M.INBOX_PROCESSING
    inbox.attempts += 1
    inbox.locked_until = now + timedelta(minutes=5)
    db.flush()

    if event is None:
        refs = inbox.event_refs or {}
        event = NormalizedProviderEvent(
            provider=inbox.provider,
            event_id=inbox.provider_event_id,
            event_type=str(refs.get("event_type") or inbox.event_type),
            provider_order_id=refs.get("order_id"),  # type: ignore[arg-type]
            provider_payment_id=refs.get("payment_id"),  # type: ignore[arg-type]
            amount_minor=refs.get("amount_minor"),  # type: ignore[arg-type]
            currency=refs.get("currency"),  # type: ignore[arg-type]
            occurred_at_epoch=None,
            raw_digest=inbox.payload_digest,
            refund_amount_minor=refs.get("refund_amount_minor"),  # type: ignore[arg-type]
        )

    try:
        txn = _apply_normalized_event(db, event=event)
        inbox.status = M.INBOX_PROCESSED
        inbox.processed_at = utcnow()
        inbox.related_transaction_id = txn.id if txn else None
        inbox.tenant_id = txn.tenant_id if txn else None
        inbox.last_error = None
        inbox.next_attempt_at = None
        inbox.locked_until = None
        log.info(
            "saas_webhook_processed provider=%s event_id=%s type=%s txn=%s",
            event.provider,
            event.event_id,
            event.event_type,
            str(txn.id) if txn else "-",
        )
        return {"status": "processed", "inbox_id": str(inbox.id)}
    except Exception as exc:  # noqa: BLE001 — durable failure classification
        err = _safe_err(exc)
        code = getattr(exc, "code", None)
        permanent = code in _PERMANENT_CODES or inbox.attempts >= max_att
        inbox.last_error = err[:500]
        inbox.locked_until = None
        if permanent:
            inbox.status = M.INBOX_PERMANENT
            inbox.next_attempt_at = None
            log.warning(
                "saas_webhook_permanent provider=%s event_id=%s err=%s attempts=%s",
                event.provider,
                event.event_id,
                type(exc).__name__,
                inbox.attempts,
            )
            return {
                "status": "permanent_failure",
                "inbox_id": str(inbox.id),
                "error": err[:200],
            }
        inbox.status = M.INBOX_RETRYABLE
        inbox.next_attempt_at = now + backoff_for_attempt(inbox.attempts)
        log.warning(
            "saas_webhook_retryable provider=%s event_id=%s err=%s attempts=%s",
            event.provider,
            event.event_id,
            type(exc).__name__,
            inbox.attempts,
        )
        return {
            "status": "retryable_failure",
            "inbox_id": str(inbox.id),
            "error": err[:200],
        }


def process_due_webhooks(db: DBSession, *, limit: int = 20) -> dict[str, Any]:
    """Claim due inbox rows with SKIP LOCKED and process. Platform/ops path."""
    now = utcnow()
    capped = min(max(limit, 1), 100)
    rows = db.execute(
        text(
            """
            SELECT id FROM saas_webhook_inbox
            WHERE status IN ('pending', 'retryable_failure')
              AND (next_attempt_at IS NULL OR next_attempt_at <= :now)
              AND (locked_until IS NULL OR locked_until < :now)
            ORDER BY received_at ASC
            LIMIT :lim
            FOR UPDATE SKIP LOCKED
            """
        ),
        {"now": now, "lim": capped},
    ).fetchall()
    results: list[dict[str, Any]] = []
    for (row_id,) in rows:
        inbox = db.get(M.SaasWebhookInbox, row_id)
        if inbox is None:
            continue
        results.append(_process_inbox_row(db, inbox=inbox, event=None))
    return {"processed": len(results), "results": results}


def replay_webhook(db: DBSession, *, inbox_id: uuid.UUID) -> dict[str, Any]:
    """Platform-admin safe replay of a durable inbox row (not unverified payment)."""
    inbox = db.get(M.SaasWebhookInbox, inbox_id)
    if inbox is None:
        raise NotFoundError("webhook inbox row not found")
    if inbox.status == M.INBOX_PROCESSED:
        return {"status": "duplicate", "inbox_id": str(inbox.id)}
    if inbox.status not in (
        M.INBOX_RETRYABLE,
        M.INBOX_PERMANENT,
        M.INBOX_PENDING,
        M.INBOX_PROCESSING,
    ):
        raise ConflictError("inbox row is not replayable")
    inbox.status = M.INBOX_PENDING
    inbox.next_attempt_at = utcnow()
    inbox.locked_until = None
    return _process_inbox_row(db, inbox=inbox, event=None)


def list_inbox(
    db: DBSession, *, status: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    capped = min(max(limit, 1), 100)
    q = select(M.SaasWebhookInbox).order_by(
        M.SaasWebhookInbox.received_at.desc(), M.SaasWebhookInbox.id.desc()
    )
    if status:
        q = q.where(M.SaasWebhookInbox.status == status)
    rows = db.execute(q.limit(capped)).scalars().all()
    return [
        {
            "id": r.id,
            "provider": r.provider,
            "provider_event_id": r.provider_event_id,
            "event_type": r.event_type,
            "status": r.status,
            "attempts": r.attempts,
            "last_error": r.last_error,
            "tenant_id": r.tenant_id,
            "related_transaction_id": r.related_transaction_id,
            "received_at": r.received_at,
            "processed_at": r.processed_at,
            "next_attempt_at": r.next_attempt_at,
            "event_refs": r.event_refs,
        }
        for r in rows
    ]


def _find_txn_for_event(
    db: DBSession, *, event: NormalizedProviderEvent
) -> M.SaasPaymentTransaction | None:
    if event.provider_order_id:
        txn = db.execute(
            select(M.SaasPaymentTransaction)
            .where(
                M.SaasPaymentTransaction.provider == event.provider,
                M.SaasPaymentTransaction.provider_order_id == event.provider_order_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if txn is not None:
            return txn
    if event.provider_payment_id:
        return db.execute(
            select(M.SaasPaymentTransaction)
            .where(
                M.SaasPaymentTransaction.provider == event.provider,
                M.SaasPaymentTransaction.provider_payment_id == event.provider_payment_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
    return None


def _apply_normalized_event(
    db: DBSession, *, event: NormalizedProviderEvent
) -> M.SaasPaymentTransaction | None:
    txn = _find_txn_for_event(db, event=event)
    if txn is None:
        log.info(
            "saas_webhook_ignored_unknown_order provider=%s order=%s",
            event.provider,
            event.provider_order_id,
        )
        return None

    db.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"),
        {"t": str(txn.tenant_id)},
    )

    if event.event_type == "payment.failed" and txn.status in (
        M.TXN_PAID,
        M.TXN_PARTIAL_REFUND,
        M.TXN_REFUNDED,
    ):
        log.info("saas_webhook_ignored_stale_failure txn=%s", str(txn.id))
        return txn

    if event.event_type == "payment.captured":
        return _apply_payment_captured(db, txn=txn, event=event)
    if event.event_type == "payment.failed":
        return _apply_payment_failed(db, txn=txn, event=event)
    if event.event_type == "refund.processed":
        return _apply_refund(db, txn=txn, event=event)
    if event.event_type == "payment.dispute":
        return _apply_dispute(db, txn=txn, event=event)
    log.info("saas_webhook_ignored_type type=%s", event.event_type)
    return txn


def _apply_payment_captured(
    db: DBSession,
    *,
    txn: M.SaasPaymentTransaction,
    event: NormalizedProviderEvent,
) -> M.SaasPaymentTransaction:
    if event.amount_minor is not None and event.amount_minor != txn.amount_minor:
        raise ConflictError("payment amount does not match checkout snapshot")
    if event.currency is not None and event.currency.upper() != txn.currency:
        raise ConflictError("payment currency does not match checkout snapshot")

    if txn.status == M.TXN_PAID:
        return txn  # idempotent success / duplicate capture

    if txn.status in (M.TXN_REFUNDED, M.TXN_PARTIAL_REFUND, M.TXN_DISPUTED):
        raise ConflictError("cannot capture against refunded/disputed transaction")

    now = utcnow()
    txn.status = M.TXN_PAID
    txn.provider_payment_id = event.provider_payment_id or txn.provider_payment_id
    txn.paid_at = now
    txn.failure_reason = None
    txn.updated_at = now
    db.flush()

    plan = db.get(SubscriptionPlan, txn.plan_id)
    if plan is None:
        raise NotFoundError("plan missing for paid transaction")

    actor_id = txn.created_by
    if actor_id is None:
        raise ConflictError("paid transaction missing created_by actor")

    sub = subs_svc.require_subscription(db, tenant_id=txn.tenant_id)
    if sub.status == "cancelled":
        # Reactivation path: expired reopen via assign is not allowed from cancelled.
        raise ConflictError("cannot apply payment to cancelled subscription")
    if sub.plan_id != plan.id or sub.status in ("expired", "trial"):
        subs_svc.assign_plan(
            db,
            tenant_id=txn.tenant_id,
            actor_id=actor_id,
            plan_code=plan.code,
            note=f"saas_payment:{txn.id}",
            target_status="active",
        )
    elif sub.status != "active":
        if sub.status in ("past_due", "grace", "suspended"):
            subs_svc.transition_status(
                db,
                tenant_id=txn.tenant_id,
                actor_id=actor_id,
                new_status="active",
                note=f"saas_payment:{txn.id}",
            )

    sub = subs_svc.require_subscription(db, tenant_id=txn.tenant_id)
    sub.period_start = txn.period_start or now
    sub.period_end = txn.period_end or (now + timedelta(days=30))
    sub.grace_ends_at = None
    sub.cancel_at_period_end = False
    sub.updated_at = now
    db.flush()
    return txn


def _apply_payment_failed(
    db: DBSession,
    *,
    txn: M.SaasPaymentTransaction,
    event: NormalizedProviderEvent,
) -> M.SaasPaymentTransaction:
    if txn.status == M.TXN_PAID:
        return txn
    now = utcnow()
    txn.status = M.TXN_FAILED
    txn.failure_reason = "provider_payment_failed"
    txn.provider_payment_id = event.provider_payment_id or txn.provider_payment_id
    txn.updated_at = now
    db.flush()

    actor_id = txn.created_by
    if actor_id is None:
        return txn
    sub = subs_svc.require_subscription(db, tenant_id=txn.tenant_id)
    if sub.status == "active":
        subs_svc.transition_status(
            db,
            tenant_id=txn.tenant_id,
            actor_id=actor_id,
            new_status="past_due",
            note=f"saas_payment_failed:{txn.id}",
        )
        subs_svc.transition_status(
            db,
            tenant_id=txn.tenant_id,
            actor_id=actor_id,
            new_status="grace",
            note=f"saas_dunning:{txn.id}",
            grace_ends_at=now + timedelta(days=_grace_days()),
        )
    return txn


def _apply_refund(
    db: DBSession,
    *,
    txn: M.SaasPaymentTransaction,
    event: NormalizedProviderEvent,
) -> M.SaasPaymentTransaction:
    """Apply refund to transaction only. Does NOT auto-cancel subscription.

    Partial vs full is determined by cumulative refunded_amount_minor.
    Subscription entitlement continues until period_end unless an operator
    cancels explicitly.
    """
    if txn.status not in (
        M.TXN_PAID,
        M.TXN_PARTIAL_REFUND,
        M.TXN_REFUNDED,
    ):
        raise ConflictError("refund requires a paid transaction")

    if txn.status == M.TXN_REFUNDED:
        return txn  # idempotent full refund

    refund_amt = event.refund_amount_minor
    if refund_amt is None:
        # Unknown amount — treat as full only when provider omits amount.
        refund_amt = txn.amount_minor - txn.refunded_amount_minor
    if refund_amt <= 0:
        raise ValidationError("refund amount must be positive")

    remaining = txn.amount_minor - txn.refunded_amount_minor
    if refund_amt > remaining:
        raise ConflictError("refund exceeds remaining paid amount")

    now = utcnow()
    txn.refunded_amount_minor += refund_amt
    if txn.refunded_amount_minor >= txn.amount_minor:
        txn.status = M.TXN_REFUNDED
    else:
        txn.status = M.TXN_PARTIAL_REFUND
    txn.updated_at = now
    db.flush()
    log.info(
        "saas_refund_applied txn=%s refunded=%s status=%s (subscription unchanged)",
        str(txn.id),
        txn.refunded_amount_minor,
        txn.status,
    )
    return txn


def _apply_dispute(
    db: DBSession,
    *,
    txn: M.SaasPaymentTransaction,
    event: NormalizedProviderEvent,
) -> M.SaasPaymentTransaction:
    """Mark transaction disputed. Subscription not auto-cancelled."""
    _ = event
    if txn.status == M.TXN_DISPUTED:
        return txn
    now = utcnow()
    txn.status = M.TXN_DISPUTED
    txn.failure_reason = "provider_dispute"
    txn.updated_at = now
    db.flush()
    return txn


def request_cancel(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    reason: str,
    at_period_end: bool = False,
    is_platform_admin: bool = False,
) -> Subscription:
    assert_checkout_actor(
        db,
        tenant_id=tenant_id,
        user_id=actor_id,
        is_platform_admin=is_platform_admin,
    )
    sub = subs_svc.require_subscription(db, tenant_id=tenant_id)
    if sub.status in ("cancelled", "expired"):
        return sub
    if at_period_end:
        if sub.status not in ("active", "past_due", "grace", "trial"):
            raise ConflictError("cancel_at_period_end not allowed in current status")
        sub.cancel_at_period_end = True
        sub.cancel_reason = reason
        sub.updated_at = utcnow()
        db.flush()
        return sub
    return subs_svc.transition_status(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        new_status="cancelled",
        note="owner_cancel",
        cancel_reason=reason,
    )


# Back-compat alias used by API.
def request_cancel_at_period_end(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    reason: str,
    is_platform_admin: bool = False,
    at_period_end: bool = False,
) -> Subscription:
    return request_cancel(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        reason=reason,
        at_period_end=at_period_end,
        is_platform_admin=is_platform_admin,
    )


def reconcile_tenant(db: DBSession, *, tenant_id: uuid.UUID) -> dict[str, Any]:
    """Compare internal SaaS payment state vs subscription (+ provider when possible)."""
    sub = subs_svc.get_subscription(db, tenant_id=tenant_id)
    txns = (
        db.execute(
            select(M.SaasPaymentTransaction).where(
                M.SaasPaymentTransaction.tenant_id == tenant_id
            )
        )
        .scalars()
        .all()
    )
    findings: list[str] = []
    paid = [t for t in txns if t.status in (M.TXN_PAID, M.TXN_PARTIAL_REFUND)]
    pending = [t for t in txns if t.status == M.TXN_PENDING]
    refunded = [t for t in txns if t.status == M.TXN_REFUNDED]
    provider = get_provider()

    for t in paid:
        if not t.provider_payment_id:
            findings.append(f"paid_without_provider_payment_id:{t.id}")
            continue
        try:
            remote = provider.fetch_payment_status(
                provider_payment_id=t.provider_payment_id
            )
            remote_status = str(remote.get("status") or "").lower()
            if remote_status and remote_status not in (
                "captured",
                "authorized",
                "refunded",
                "partially_refunded",
            ):
                findings.append(f"provider_does_not_confirm_capture:{t.id}")
            remote_amt = remote.get("amount")
            if remote_amt is not None and int(remote_amt) != t.amount_minor:
                findings.append(f"amount_mismatch:{t.id}")
            remote_cur = remote.get("currency")
            if remote_cur and str(remote_cur).upper() != t.currency:
                findings.append(f"currency_mismatch:{t.id}")
        except Exception as exc:  # noqa: BLE001
            findings.append(f"provider_fetch_failed:{type(exc).__name__}")

    if sub is None:
        findings.append("missing_subscription")
    else:
        if sub.status == "active" and not paid and sub.plan_id:
            plan = db.get(SubscriptionPlan, sub.plan_id)
            if plan is not None and plan.price_minor > 0:
                findings.append("active_without_paid_saas_transaction")
        if paid and sub.status in ("past_due", "grace"):
            latest = max(paid, key=lambda t: t.paid_at or t.created_at)
            findings.append("delinquent_with_paid_transaction")
            _apply_payment_captured(
                db,
                txn=latest,
                event=NormalizedProviderEvent(
                    provider=latest.provider,
                    event_id=f"reconcile-{latest.id}",
                    event_type="payment.captured",
                    provider_order_id=latest.provider_order_id,
                    provider_payment_id=latest.provider_payment_id,
                    amount_minor=latest.amount_minor,
                    currency=latest.currency,
                    occurred_at_epoch=None,
                    raw_digest="reconcile",
                ),
            )
            findings.append("healed_to_active")
        if sub.cancel_at_period_end and sub.period_end and utcnow() >= sub.period_end:
            findings.append("cancel_at_period_end_due")
        stale = [
            t for t in pending if (utcnow() - t.created_at).total_seconds() > 86400
        ]
        if stale:
            findings.append(f"stale_pending_transactions:{len(stale)}")
        # Provider captured but internal still pending — heal via payment id lookup.
        for t in pending:
            if not t.provider_payment_id:
                continue
            try:
                remote = provider.fetch_payment_status(
                    provider_payment_id=t.provider_payment_id
                )
            except Exception as exc:  # noqa: BLE001
                log.info(
                    "saas_reconcile_fetch_skip txn=%s err=%s",
                    str(t.id),
                    type(exc).__name__,
                )
                continue
            if str(remote.get("status") or "").lower() == "captured":
                findings.append(f"provider_captured_internal_pending:{t.id}")
                _apply_payment_captured(
                    db,
                    txn=t,
                    event=NormalizedProviderEvent(
                        provider=t.provider,
                        event_id=f"reconcile-cap-{t.id}",
                        event_type="payment.captured",
                        provider_order_id=t.provider_order_id,
                        provider_payment_id=t.provider_payment_id,
                        amount_minor=t.amount_minor,
                        currency=t.currency,
                        occurred_at_epoch=None,
                        raw_digest="reconcile",
                    ),
                )
                findings.append(f"healed_pending_to_paid:{t.id}")

    open_inbox = db.execute(
        select(M.SaasWebhookInbox).where(
            M.SaasWebhookInbox.tenant_id == tenant_id,
            M.SaasWebhookInbox.status.in_(
                [M.INBOX_RETRYABLE, M.INBOX_PERMANENT, M.INBOX_PENDING]
            ),
        )
    ).scalars().all()
    if open_inbox:
        findings.append(f"open_webhook_inbox:{len(open_inbox)}")

    log.info(
        "saas_reconcile tenant_id=%s findings=%s paid=%s pending=%s refunded=%s",
        str(tenant_id),
        ",".join(findings) or "-",
        len(paid),
        len(pending),
        len(refunded),
    )
    return {
        "tenant_id": tenant_id,
        "subscription_status": sub.status if sub else None,
        "paid_count": len(paid),
        "pending_count": len(pending),
        "refunded_count": len(refunded),
        "findings": findings,
    }


def lock_saas_tenant(db: DBSession, *, tenant_id: uuid.UUID) -> None:
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key)::bigint)"),
        {"key": f"saas_pay:{tenant_id}"},
    )
