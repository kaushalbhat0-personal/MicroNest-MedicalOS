"""Subscription service (O1.2a): trial plan lookup + trial subscription issue.

The ONLY writer of `subscriptions` in O1 is workspace provisioning. Plan
and status are server-resolved — never accepted from client input — so a
caller cannot manipulate trial status, plan entitlements, or ownership.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.modules.subscriptions.models import (
    TRIAL_PLAN_CODE,
    TRIAL_STATUS,
    Subscription,
    SubscriptionPlan,
)
from app.modules.tenancy.models import Tenant
from app.modules.tenancy.schemas import PlanLimits, SubscriptionSummary
from app.platform import ids
from app.platform.errors import NotFoundError
from app.platform.time import now as utcnow


def get_plan_by_code(db: DBSession, *, code: str) -> SubscriptionPlan:
    """Deterministic single-row plan lookup.

    `code` is UNIQUE, so at most one row exists; the explicit ordering makes
    the resolution order deterministic by construction (and stable even if
    the constraint were ever relaxed). Missing plans fail closed.
    """
    plan = db.execute(
        select(SubscriptionPlan)
        .where(SubscriptionPlan.code == code)
        .order_by(SubscriptionPlan.created_at.asc())
    ).scalar_one_or_none()
    if plan is None:
        raise NotFoundError(f"subscription plan {code!r} missing")
    return plan


def get_trial_plan(db: DBSession) -> SubscriptionPlan:
    """Resolve the initial trial plan. Inactive plans fail closed: a trial
    must never be issued from a deactivated catalog row."""
    plan = get_plan_by_code(db, code=TRIAL_PLAN_CODE)
    if not plan.is_active:
        raise NotFoundError(f"subscription plan {TRIAL_PLAN_CODE!r} is not active")
    return plan


def get_subscription(db: DBSession, *, tenant_id: object) -> Subscription | None:
    return db.execute(
        select(Subscription).where(Subscription.tenant_id == tenant_id)  # type: ignore[arg-type]
    ).scalar_one_or_none()


def subscriptions_for_tenants(
    db: DBSession, *, tenant_ids: Sequence[object]
) -> dict[object, Subscription]:
    """Batch subscription lookup for platform reads (single query, no N+1)."""
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
    """Batch plan lookup for platform reads (single query, no N+1)."""
    if not plan_ids:
        return {}
    rows = (
        db.execute(select(SubscriptionPlan).where(SubscriptionPlan.id.in_(plan_ids)))
        .scalars()
        .all()
    )
    return {r.id: r for r in rows}


def create_trial_subscription(db: DBSession, *, tenant: Tenant) -> Subscription:
    """Issue the initial 14-day trial for a newly provisioned tenant.

    No payment method, no automatic charge, no gateway call. The trial end
    derives from the seeded plan's `trial_days` (14), not from client input.
    """
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
    return sub


def build_summary(
    subscription: Subscription, plan: SubscriptionPlan | None
) -> SubscriptionSummary:
    """Server-resolved read snapshot shared by tenant + platform views.

    Single source for `is_in_trial` semantics: status "trial" AND the
    persisted trial window still covering now. Derived only — never written
    back, never enforced. Limits are informational (`enforced=False`).
    """
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
                enforced=False,
            )
            if plan is not None
            else None
        ),
    )
