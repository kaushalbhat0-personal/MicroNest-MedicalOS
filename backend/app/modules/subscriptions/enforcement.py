"""P2.2 atomic entitlement enforcement for staff seats, locations, practitioners.

Builds on P2.1 ``resolve_entitlements`` / usage measurement. Uses a
tenant-scoped PostgreSQL advisory transaction lock so check-then-write is
atomic under READ COMMITTED — same pattern as scheduling/billing.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session as DBSession

from app.modules.subscriptions import entitlements as ent
from app.modules.subscriptions.commercial_policy import (
    CAPACITY_EXPAND_STATUSES as EXPANDING_WRITE_STATUSES,
)
from app.modules.subscriptions.models import Subscription, SubscriptionPlan
from app.modules.tenancy.models import Invitation, Role
from app.platform.errors import EntitlementExceededError
from app.platform.time import now as utcnow

log = logging.getLogger("healthcare_os.entitlements")

ENFORCED_LIMIT_KEYS = frozenset({"max_staff_seats", "max_locations", "max_practitioners"})
# Capacity expand: trial/active only (P2.3). Business creates use commercial_policy.

CapacityKind = Literal["max_staff_seats", "max_locations", "max_practitioners"]


@dataclass(frozen=True)
class CapacityDecision:
    allowed: bool
    entitlement_key: str
    usage: int
    limit: int | None
    reason_code: str
    would_deny_if_enforced: bool = True


def lock_tenant_capacity(db: DBSession, *, tenant_id: uuid.UUID) -> None:
    """Serialize all capacity-consuming writes for one tenant in this txn."""
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key)::bigint)"),
        {"key": f"entitlement:{tenant_id}"},
    )


def count_pending_staff_invite_reservations(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    exclude_invitation_id: uuid.UUID | None = None,
) -> int:
    """Pending, unexpired invitations for non-patient roles.

    Soft-expired rows that remain ``pending`` do **not** reserve capacity
    (``expires_at > now``). Revoked/accepted never reserve. Patient-role
    invitations (if any) are excluded.
    """
    stmt = (
        select(func.count())
        .select_from(Invitation)
        .join(Role, Role.id == Invitation.role_id)
        .where(
            Invitation.tenant_id == tenant_id,
            Invitation.status == "pending",
            Invitation.expires_at > utcnow(),
            Role.name != "patient",
        )
    )
    if exclude_invitation_id is not None:
        stmt = stmt.where(Invitation.id != exclude_invitation_id)
    return int(db.execute(stmt).scalar_one())


def staff_seat_usage(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    exclude_invitation_id: uuid.UUID | None = None,
) -> dict[str, int]:
    """Canonical seat consumption = active seats + pending reservations."""
    seats = ent.count_staff_seats(db, tenant_id=tenant_id)
    reserved = count_pending_staff_invite_reservations(
        db, tenant_id=tenant_id, exclude_invitation_id=exclude_invitation_id
    )
    return {
        "active_memberships": seats,
        "pending_reservations": reserved,
        "consumed": seats + reserved,
    }


def _plan_and_subscription(
    db: DBSession, *, tenant_id: uuid.UUID
) -> tuple[Subscription | None, SubscriptionPlan | None]:
    sub = db.execute(
        select(Subscription).where(Subscription.tenant_id == tenant_id)
    ).scalar_one_or_none()
    plan = db.get(SubscriptionPlan, sub.plan_id) if sub is not None else None
    return sub, plan


def require_expanding_write_eligible(db: DBSession, *, tenant_id: uuid.UUID) -> Subscription:
    """Deny capacity-expanding writes when commercial status is inactive/missing."""
    sub, _plan = _plan_and_subscription(db, tenant_id=tenant_id)
    if sub is None:
        raise EntitlementExceededError(
            "subscription required for this operation",
            entitlement_key=None,
            reason_code="missing_subscription",
        )
    if sub.status not in EXPANDING_WRITE_STATUSES:
        raise EntitlementExceededError(
            f"subscription status '{sub.status}' does not allow capacity expansion",
            entitlement_key=None,
            reason_code="subscription_inactive",
        )
    return sub


def evaluate_capacity(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    entitlement_key: CapacityKind,
    delta: int = 1,
    exclude_invitation_id: uuid.UUID | None = None,
) -> CapacityDecision:
    """Read usage+limit under caller-held lock. Does not raise."""
    _sub, plan = _plan_and_subscription(db, tenant_id=tenant_id)
    if plan is None:
        return CapacityDecision(
            allowed=False,
            entitlement_key=entitlement_key,
            usage=0,
            limit=None,
            reason_code="missing_plan_revision",
        )

    if entitlement_key == "max_staff_seats":
        usage_map = staff_seat_usage(
            db, tenant_id=tenant_id, exclude_invitation_id=exclude_invitation_id
        )
        usage = usage_map["consumed"]
        limit = plan.max_staff_seats
    elif entitlement_key == "max_locations":
        usage = ent.count_active_locations(db, tenant_id=tenant_id)
        limit = plan.max_locations
    elif entitlement_key == "max_practitioners":
        usage = ent.count_approved_practitioners(db, tenant_id=tenant_id)
        limit = plan.max_practitioners
    else:
        return CapacityDecision(
            allowed=False,
            entitlement_key=entitlement_key,
            usage=0,
            limit=None,
            reason_code="unknown_entitlement_key",
        )

    projected = usage + max(delta, 0)
    if projected > limit:
        return CapacityDecision(
            allowed=False,
            entitlement_key=entitlement_key,
            usage=usage,
            limit=limit,
            reason_code="would_exceed_limit",
        )
    return CapacityDecision(
        allowed=True,
        entitlement_key=entitlement_key,
        usage=usage,
        limit=limit,
        reason_code="within_limit",
        would_deny_if_enforced=False,
    )


def assert_capacity(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    entitlement_key: CapacityKind,
    delta: int = 1,
    exclude_invitation_id: uuid.UUID | None = None,
    enforce_subscription: bool = True,
) -> CapacityDecision:
    """Lock → subscription gate → measure → decide. Raises on deny."""
    lock_tenant_capacity(db, tenant_id=tenant_id)
    if enforce_subscription:
        require_expanding_write_eligible(db, tenant_id=tenant_id)
    decision = evaluate_capacity(
        db,
        tenant_id=tenant_id,
        entitlement_key=entitlement_key,
        delta=delta,
        exclude_invitation_id=exclude_invitation_id,
    )
    log.info(
        "entitlement_capacity_check tenant_id=%s key=%s delta=%s usage=%s limit=%s "
        "allowed=%s reason=%s",
        str(tenant_id),
        entitlement_key,
        delta,
        decision.usage,
        decision.limit,
        decision.allowed,
        decision.reason_code,
    )
    if not decision.allowed:
        raise EntitlementExceededError(
            (
                f"{entitlement_key} capacity exceeded "
                f"(usage={decision.usage}, limit={decision.limit})"
            ),
            entitlement_key=entitlement_key,
            reason_code=decision.reason_code,
        )
    return decision


def role_consumes_staff_seat(role: Role) -> bool:
    return role.name != "patient"
