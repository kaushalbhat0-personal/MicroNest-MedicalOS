"""Subscription service: catalog reads + validated commercial writes.

Writers: workspace provisioning (trial create) and authorized admin
operations (assign plan / transition / extend trial). Plan and status are
never accepted as free-form client ownership — tenant_id comes from the
server context / platform path.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.modules.subscriptions.models import (
    BILLING_INTERVALS,
    EVENT_CREATED,
    EVENT_PLAN,
    EVENT_STATUS,
    EVENT_TRIAL_EXT,
    STATUS_TRANSITIONS,
    SUBSCRIPTION_STATUSES,
    TERMINAL_STATUSES,
    TRIAL_PLAN_CODE,
    TRIAL_STATUS,
    Subscription,
    SubscriptionEvent,
    SubscriptionPlan,
)
from app.modules.tenancy.models import Tenant
from app.modules.tenancy.schemas import PlanLimits, SubscriptionSummary
from app.platform import ids
from app.platform.errors import ConflictError, NotFoundError, ValidationError
from app.platform.time import now as utcnow


def get_plan_by_code(db: DBSession, *, code: str) -> SubscriptionPlan:
    plan = db.execute(
        select(SubscriptionPlan)
        .where(SubscriptionPlan.code == code)
        .order_by(SubscriptionPlan.created_at.asc())
    ).scalar_one_or_none()
    if plan is None:
        raise NotFoundError(f"subscription plan {code!r} missing")
    return plan


def get_trial_plan(db: DBSession) -> SubscriptionPlan:
    plan = get_plan_by_code(db, code=TRIAL_PLAN_CODE)
    if not plan.is_active:
        raise NotFoundError(f"subscription plan {TRIAL_PLAN_CODE!r} is not active")
    return plan


def get_subscription(db: DBSession, *, tenant_id: object) -> Subscription | None:
    return db.execute(
        select(Subscription).where(Subscription.tenant_id == tenant_id)  # type: ignore[arg-type]
    ).scalar_one_or_none()


def require_subscription(db: DBSession, *, tenant_id: uuid.UUID) -> Subscription:
    sub = get_subscription(db, tenant_id=tenant_id)
    if sub is None:
        raise NotFoundError("subscription not found")
    return sub


def subscriptions_for_tenants(
    db: DBSession, *, tenant_ids: Sequence[object]
) -> dict[object, Subscription]:
    if not tenant_ids:
        return {}
    rows = (
        db.execute(select(Subscription).where(Subscription.tenant_id.in_(tenant_ids)))
        .scalars()
        .all()
    )
    return {r.tenant_id: r for r in rows}


def plans_by_ids(
    db: DBSession, *, plan_ids: Sequence[object]
) -> dict[object, SubscriptionPlan]:
    if not plan_ids:
        return {}
    rows = (
        db.execute(select(SubscriptionPlan).where(SubscriptionPlan.id.in_(plan_ids)))
        .scalars()
        .all()
    )
    return {r.id: r for r in rows}


def list_active_plans(db: DBSession) -> list[SubscriptionPlan]:
    """Public catalog: active revisions only, newest version per family first."""
    rows = list(
        db.execute(
            select(SubscriptionPlan)
            .where(SubscriptionPlan.is_active.is_(True))
            .order_by(SubscriptionPlan.family_code.asc(), SubscriptionPlan.version.desc())
        )
        .scalars()
        .all()
    )
    # One visible row per family (highest version among active).
    seen: set[str] = set()
    out: list[SubscriptionPlan] = []
    for p in rows:
        if p.family_code in seen:
            continue
        seen.add(p.family_code)
        out.append(p)
    return out


def list_plan_versions(db: DBSession, *, family_code: str) -> list[SubscriptionPlan]:
    return list(
        db.execute(
            select(SubscriptionPlan)
            .where(SubscriptionPlan.family_code == family_code)
            .order_by(SubscriptionPlan.version.desc())
        )
        .scalars()
        .all()
    )


def _record_event(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    subscription_id: uuid.UUID,
    event_type: str,
    from_status: str | None = None,
    to_status: str | None = None,
    from_plan_id: uuid.UUID | None = None,
    to_plan_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    note: str | None = None,
    at: object | None = None,
) -> SubscriptionEvent:
    ts = at or utcnow()
    ev = SubscriptionEvent(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        subscription_id=subscription_id,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        from_plan_id=from_plan_id,
        to_plan_id=to_plan_id,
        actor_id=actor_id,
        note=(note or "").strip() or None,
        created_at=ts,  # type: ignore[arg-type]
    )
    db.add(ev)
    db.flush()
    return ev


def create_trial_subscription(db: DBSession, *, tenant: Tenant) -> Subscription:
    """Issue the initial 14-day trial for a newly provisioned tenant."""
    existing = get_subscription(db, tenant_id=tenant.id)
    if existing is not None:
        raise ConflictError("tenant already has a subscription")
    plan = get_trial_plan(db)
    now = utcnow()
    trial_ends_at = now + timedelta(days=int(plan.trial_days))
    sub = Subscription(
        id=ids.uuid7(),
        tenant_id=tenant.id,
        plan_id=plan.id,
        status=TRIAL_STATUS,
        trial_ends_at=trial_ends_at,
        period_start=now,
        period_end=trial_ends_at,
        created_at=now,
        updated_at=now,
    )
    db.add(sub)
    db.flush()
    _record_event(
        db,
        tenant_id=tenant.id,
        subscription_id=sub.id,
        event_type=EVENT_CREATED,
        to_status=TRIAL_STATUS,
        to_plan_id=plan.id,
        note="trial issued at workspace provision",
        at=now,
    )
    return sub


def build_summary(
    subscription: Subscription, plan: SubscriptionPlan | None
) -> SubscriptionSummary:
    """Server-resolved read snapshot. Limits remain informational."""
    now = utcnow()
    trial_ends_at = subscription.trial_ends_at
    return SubscriptionSummary(
        status=subscription.status,
        trial_ends_at=trial_ends_at,
        plan_code=plan.code if plan is not None else TRIAL_PLAN_CODE,
        plan_name=plan.name if plan is not None else "",
        trial_starts_at=subscription.period_start,
        is_in_trial=(
            subscription.status == "trial"
            and (trial_ends_at is None or now <= trial_ends_at)
        ),
        limits=(
            PlanLimits(
                max_locations=plan.max_locations,
                max_practitioners=plan.max_practitioners,
                max_staff_seats=plan.max_staff_seats,
                enforced=True,
            )
            if plan is not None
            else None
        ),
    )


def plan_to_dict(plan: SubscriptionPlan) -> dict[str, Any]:
    features = plan.features if isinstance(plan.features, dict) else {}
    return {
        "id": plan.id,
        "code": plan.code,
        "family_code": plan.family_code,
        "version": plan.version,
        "name": plan.name,
        "description": plan.description or "",
        "currency": plan.currency,
        "billing_interval": plan.billing_interval,
        "price_minor": int(plan.price_minor),
        "features": features,
        "limits": {
            "max_locations": plan.max_locations,
            "max_practitioners": plan.max_practitioners,
            "max_staff_seats": plan.max_staff_seats,
            "enforced": False,
        },
        "trial_days": plan.trial_days,
        "is_active": plan.is_active,
        "created_at": plan.created_at,
    }


def subscription_detail(
    db: DBSession, *, subscription: Subscription
) -> dict[str, Any]:
    plan = db.get(SubscriptionPlan, subscription.plan_id)
    if plan is None:
        raise NotFoundError("subscription plan missing")
    summary = build_summary(subscription, plan)
    return {
        "id": subscription.id,
        "tenant_id": subscription.tenant_id,
        "status": subscription.status,
        "plan": plan_to_dict(plan),
        "trial_starts_at": summary.trial_starts_at,
        "trial_ends_at": summary.trial_ends_at,
        "is_in_trial": summary.is_in_trial,
        "period_start": subscription.period_start,
        "period_end": subscription.period_end,
        "grace_ends_at": subscription.grace_ends_at,
        "cancelled_at": subscription.cancelled_at,
        "cancel_reason": subscription.cancel_reason,
        "cancel_at_period_end": bool(subscription.cancel_at_period_end),
        "provider_ref": None,  # never expose speculative provider state
        "limits_enforced": True,
        "created_at": subscription.created_at,
        "updated_at": subscription.updated_at,
    }


def list_events(
    db: DBSession, *, tenant_id: uuid.UUID, limit: int = 100
) -> list[SubscriptionEvent]:
    capped = min(max(limit, 1), 200)
    return list(
        db.execute(
            select(SubscriptionEvent)
            .where(SubscriptionEvent.tenant_id == tenant_id)
            .order_by(SubscriptionEvent.created_at.desc(), SubscriptionEvent.id.desc())
            .limit(capped)
        )
        .scalars()
        .all()
    )


def _assert_transition(current: str, new_status: str) -> None:
    if new_status not in SUBSCRIPTION_STATUSES:
        raise ValidationError(f"unknown subscription status {new_status!r}")
    allowed = STATUS_TRANSITIONS.get(current, frozenset())
    if new_status not in allowed:
        raise ConflictError(f"cannot transition {current} → {new_status}")


def transition_status(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    new_status: str,
    note: str | None = None,
    cancel_reason: str | None = None,
    grace_ends_at: object | None = None,
) -> Subscription:
    """Authorized status change. Does not mutate tenants.status (abuse axis)."""
    sub = require_subscription(db, tenant_id=tenant_id)
    _assert_transition(sub.status, new_status)
    from_status = sub.status
    now = utcnow()
    sub.status = new_status
    if new_status == "cancelled":
        reason = (cancel_reason or note or "").strip()
        if len(reason) < 2:
            raise ValidationError("cancel_reason required for cancellation")
        sub.cancelled_at = now
        sub.cancel_reason = reason[:500]
    if new_status == "grace":
        if grace_ends_at is None:
            sub.grace_ends_at = now + timedelta(days=7)
        else:
            sub.grace_ends_at = grace_ends_at  # type: ignore[assignment]
    if new_status == "active":
        sub.grace_ends_at = None
        sub.cancelled_at = None
        sub.cancel_reason = None
    if new_status in TERMINAL_STATUSES and new_status == "expired":
        sub.period_end = now
    sub.updated_at = now
    db.flush()
    _record_event(
        db,
        tenant_id=tenant_id,
        subscription_id=sub.id,
        event_type=EVENT_STATUS,
        from_status=from_status,
        to_status=new_status,
        actor_id=actor_id,
        note=note,
        at=now,
    )
    return sub


def assign_plan(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    plan_code: str,
    note: str | None = None,
    target_status: str | None = None,
) -> Subscription:
    """Assign an active catalog plan revision to the tenant subscription."""
    sub = require_subscription(db, tenant_id=tenant_id)
    plan = get_plan_by_code(db, code=plan_code)
    if not plan.is_active:
        raise ValidationError("cannot assign an inactive plan revision")
    if plan.id == sub.plan_id and (target_status is None or target_status == sub.status):
        return sub

    from_plan = sub.plan_id
    from_status = sub.status
    now = utcnow()
    sub.plan_id = plan.id

    new_status = target_status
    if new_status is None and sub.status == "trial" and plan.code != TRIAL_PLAN_CODE:
        # Catalog paid assignment typically ends trial → active (manual; no charge).
        new_status = "active"
    if new_status is not None and new_status != sub.status:
        _assert_transition(sub.status, new_status)
        sub.status = new_status
        if new_status == "active":
            sub.grace_ends_at = None
            sub.period_start = now
            if plan.billing_interval in BILLING_INTERVALS:
                days = 30 if plan.billing_interval == "month" else 365
                sub.period_end = now + timedelta(days=days)
            else:
                sub.period_end = None

    sub.updated_at = now
    db.flush()
    _record_event(
        db,
        tenant_id=tenant_id,
        subscription_id=sub.id,
        event_type=EVENT_PLAN,
        from_status=from_status,
        to_status=sub.status,
        from_plan_id=from_plan,
        to_plan_id=plan.id,
        actor_id=actor_id,
        note=note or f"assigned plan {plan.code}",
        at=now,
    )
    if new_status is not None and new_status != from_status:
        _record_event(
            db,
            tenant_id=tenant_id,
            subscription_id=sub.id,
            event_type=EVENT_STATUS,
            from_status=from_status,
            to_status=new_status,
            actor_id=actor_id,
            note=note,
            at=now,
        )
    return sub


def extend_trial(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    days: int,
    note: str | None = None,
) -> Subscription:
    if days < 1 or days > 90:
        raise ValidationError("days must be 1-90")
    sub = require_subscription(db, tenant_id=tenant_id)
    if sub.status not in ("trial", "expired"):
        raise ConflictError("trial extension only allowed from trial or expired")
    now = utcnow()
    if sub.status == "expired":
        _assert_transition("expired", "trial")
        sub.status = "trial"
        base = now
    else:
        base = sub.trial_ends_at or now
        if base < now:
            base = now
    sub.trial_ends_at = base + timedelta(days=days)
    sub.period_end = sub.trial_ends_at
    if sub.period_start is None:
        sub.period_start = now
    sub.updated_at = now
    db.flush()
    _record_event(
        db,
        tenant_id=tenant_id,
        subscription_id=sub.id,
        event_type=EVENT_TRIAL_EXT,
        from_status="trial" if sub.status == "trial" else "expired",
        to_status="trial",
        to_plan_id=sub.plan_id,
        actor_id=actor_id,
        note=note or f"extended trial by {days} day(s)",
        at=now,
    )
    return sub


def create_plan_revision(
    db: DBSession,
    *,
    family_code: str,
    name: str,
    description: str,
    max_locations: int,
    max_practitioners: int,
    max_staff_seats: int,
    price_minor: int = 0,
    billing_interval: str | None = "month",
    trial_days: int = 0,
    features: dict[str, Any] | None = None,
    deactivate_prior: bool = True,
) -> SubscriptionPlan:
    """Platform/migration helper: insert immutable next version for a family."""
    if billing_interval is not None and billing_interval not in BILLING_INTERVALS:
        raise ValidationError("billing_interval must be month, year, or null")
    if price_minor < 0:
        raise ValidationError("price_minor must be >= 0")
    prior = list_plan_versions(db, family_code=family_code)
    next_version = (prior[0].version + 1) if prior else 1
    code = f"{family_code}-v{next_version}"
    now = utcnow()
    plan = SubscriptionPlan(
        id=ids.uuid7(),
        code=code,
        family_code=family_code,
        version=next_version,
        name=name,
        description=description,
        currency="INR",
        billing_interval=billing_interval,
        price_minor=price_minor,
        features=features or {},
        max_locations=max_locations,
        max_practitioners=max_practitioners,
        max_staff_seats=max_staff_seats,
        trial_days=trial_days,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(plan)
    db.flush()
    if deactivate_prior:
        for old in prior:
            if old.is_active:
                old.is_active = False
                old.updated_at = now
        db.flush()
    return plan
