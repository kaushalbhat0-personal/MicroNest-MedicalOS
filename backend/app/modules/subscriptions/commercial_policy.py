"""P2.3 commercial state gates + feature enforcement policy.

Axes (independent):
1. User permissions (require / RBAC) — unchanged, authoritative for who may act.
2. Abuse/security tenant status (``tenants.status`` via ``get_ctx``) — unchanged.
3. Commercial subscription status — this module.
4. Plan feature flags — this module.
5. Numeric capacity — ``enforcement.assert_capacity`` (P2.2).

Patient portal *access* (reads, cancel) is intentionally **not** denied by
commercial delinquency. Abuse suspension still blocks via ``get_ctx``.
New portal enrollment is a staff-side expansion gated by commercial + feature.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.modules.subscriptions import entitlements as ent
from app.modules.subscriptions.models import Subscription, SubscriptionPlan
from app.platform.errors import EntitlementExceededError, ForbiddenError

log = logging.getLogger("healthcare_os.commercial_policy")

# Capacity-consuming expansion (seats/locations/practitioners).
CAPACITY_EXPAND_STATUSES = frozenset({"trial", "active"})

# Ongoing clinic operations: care + AR + inventory creates during dunning.
BUSINESS_CREATE_STATUSES = frozenset({"trial", "active", "past_due", "grace"})

# Feature catalog keys that P2.3 enforces end-to-end.
ENFORCED_FEATURES = frozenset(
    {
        "patient_portal",
        "inventory",
        "operations_dashboard",
        "clinic_billing",
        "staff_workforce",
    }
)


class OpCategory(str, Enum):
    CAPACITY_EXPAND = "capacity_expand"
    BUSINESS_CREATE = "business_create"
    FEATURE_MUTATE = "feature_mutate"
    FEATURE_READ = "feature_read"
    RECOVERY = "recovery"
    PATIENT_PORTAL_ACCESS = "patient_portal_access"
    PORTAL_ENROLL = "portal_enroll"
    READ = "read"


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    category: str
    subscription_status: str | None
    feature_key: str | None
    reason_code: str
    enforcement_mode: str = "enforced"


def _subscription(db: DBSession, *, tenant_id: uuid.UUID) -> Subscription | None:
    return db.execute(
        select(Subscription).where(Subscription.tenant_id == tenant_id)
    ).scalar_one_or_none()


def _plan(db: DBSession, *, sub: Subscription | None) -> SubscriptionPlan | None:
    if sub is None:
        return None
    return db.get(SubscriptionPlan, sub.plan_id)


def resolve_features(db: DBSession, *, tenant_id: uuid.UUID) -> dict[str, bool]:
    sub = _subscription(db, tenant_id=tenant_id)
    plan = _plan(db, sub=sub)
    return ent.parse_features(plan.features if plan is not None else {})


def evaluate_operation(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    category: OpCategory,
    feature_key: str | None = None,
    operation: str | None = None,
) -> PolicyDecision:
    """Pure evaluation — does not raise."""
    sub = _subscription(db, tenant_id=tenant_id)
    status = sub.status if sub is not None else None
    features = resolve_features(db, tenant_id=tenant_id)

    if category == OpCategory.RECOVERY or category == OpCategory.READ:
        return PolicyDecision(
            allowed=True,
            category=category.value,
            subscription_status=status,
            feature_key=feature_key,
            reason_code="always_allowed",
            enforcement_mode="enforced",
        )

    if category == OpCategory.PATIENT_PORTAL_ACCESS:
        # Commercial status ignored. Feature + abuse (get_ctx) gate access.
        if not features.get("patient_portal", False):
            return PolicyDecision(
                allowed=False,
                category=category.value,
                subscription_status=status,
                feature_key="patient_portal",
                reason_code="feature_not_included",
            )
        return PolicyDecision(
            allowed=True,
            category=category.value,
            subscription_status=status,
            feature_key="patient_portal",
            reason_code="portal_access_independent_of_commercial",
        )

    if category == OpCategory.CAPACITY_EXPAND:
        if sub is None:
            return PolicyDecision(
                allowed=False,
                category=category.value,
                subscription_status=None,
                feature_key=feature_key,
                reason_code="missing_subscription",
            )
        if status not in CAPACITY_EXPAND_STATUSES:
            return PolicyDecision(
                allowed=False,
                category=category.value,
                subscription_status=status,
                feature_key=feature_key,
                reason_code="subscription_inactive"
                if status in ("suspended", "cancelled", "expired")
                else "capacity_expand_not_allowed",
            )
        return PolicyDecision(
            allowed=True,
            category=category.value,
            subscription_status=status,
            feature_key=feature_key,
            reason_code="within_policy",
        )

    if category in (OpCategory.BUSINESS_CREATE, OpCategory.PORTAL_ENROLL):
        if sub is None:
            return PolicyDecision(
                allowed=False,
                category=category.value,
                subscription_status=None,
                feature_key=feature_key,
                reason_code="missing_subscription",
            )
        if status not in BUSINESS_CREATE_STATUSES:
            return PolicyDecision(
                allowed=False,
                category=category.value,
                subscription_status=status,
                feature_key=feature_key,
                reason_code="subscription_inactive",
            )
        if category == OpCategory.PORTAL_ENROLL and not features.get("patient_portal", False):
            return PolicyDecision(
                allowed=False,
                category=category.value,
                subscription_status=status,
                feature_key="patient_portal",
                reason_code="feature_not_included",
            )
        return PolicyDecision(
            allowed=True,
            category=category.value,
            subscription_status=status,
            feature_key=feature_key,
            reason_code="within_policy",
        )

    if category in (OpCategory.FEATURE_MUTATE, OpCategory.FEATURE_READ):
        if feature_key is None or feature_key not in ENFORCED_FEATURES:
            return PolicyDecision(
                allowed=False,
                category=category.value,
                subscription_status=status,
                feature_key=feature_key,
                reason_code="unknown_feature_key",
            )
        if not features.get(feature_key, False):
            return PolicyDecision(
                allowed=False,
                category=category.value,
                subscription_status=status,
                feature_key=feature_key,
                reason_code="feature_not_included",
            )
        if category == OpCategory.FEATURE_MUTATE:
            if sub is None:
                return PolicyDecision(
                    allowed=False,
                    category=category.value,
                    subscription_status=None,
                    feature_key=feature_key,
                    reason_code="missing_subscription",
                )
            if status not in BUSINESS_CREATE_STATUSES:
                return PolicyDecision(
                    allowed=False,
                    category=category.value,
                    subscription_status=status,
                    feature_key=feature_key,
                    reason_code="subscription_inactive",
                )
        return PolicyDecision(
            allowed=True,
            category=category.value,
            subscription_status=status,
            feature_key=feature_key,
            reason_code="within_policy",
        )

    return PolicyDecision(
        allowed=False,
        category=category.value,
        subscription_status=status,
        feature_key=feature_key,
        reason_code="unknown_operation_category",
    )


def _raise_denied(decision: PolicyDecision, *, detail: str | None = None) -> None:
    msg = detail or f"operation denied ({decision.reason_code})"
    # Feature exclusion is a 403; capacity/commercial conflict stays 409 family.
    if decision.reason_code == "feature_not_included":
        raise ForbiddenError(msg)
    raise EntitlementExceededError(
        msg,
        entitlement_key=decision.feature_key,
        reason_code=decision.reason_code,
    )


def assert_operation_allowed(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    category: OpCategory,
    feature_key: str | None = None,
    operation: str | None = None,
) -> PolicyDecision:
    decision = evaluate_operation(
        db,
        tenant_id=tenant_id,
        category=category,
        feature_key=feature_key,
        operation=operation,
    )
    log.info(
        "commercial_policy_decision tenant_id=%s category=%s op=%s status=%s "
        "feature=%s allowed=%s reason=%s mode=%s",
        str(tenant_id),
        decision.category,
        operation or "-",
        decision.subscription_status or "-",
        decision.feature_key or "-",
        decision.allowed,
        decision.reason_code,
        decision.enforcement_mode,
    )
    if not decision.allowed:
        _raise_denied(decision)
    return decision


def assert_business_create(db: DBSession, *, tenant_id: uuid.UUID, operation: str) -> None:
    assert_operation_allowed(
        db,
        tenant_id=tenant_id,
        category=OpCategory.BUSINESS_CREATE,
        operation=operation,
    )


def assert_feature(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    feature_key: str,
    mutate: bool = True,
    operation: str | None = None,
) -> None:
    assert_operation_allowed(
        db,
        tenant_id=tenant_id,
        category=OpCategory.FEATURE_MUTATE if mutate else OpCategory.FEATURE_READ,
        feature_key=feature_key,
        operation=operation,
    )


def assert_portal_access(db: DBSession, *, tenant_id: uuid.UUID) -> None:
    assert_operation_allowed(
        db,
        tenant_id=tenant_id,
        category=OpCategory.PATIENT_PORTAL_ACCESS,
        feature_key="patient_portal",
        operation="portal_access",
    )


def assert_portal_enroll(db: DBSession, *, tenant_id: uuid.UUID) -> None:
    assert_operation_allowed(
        db,
        tenant_id=tenant_id,
        category=OpCategory.PORTAL_ENROLL,
        feature_key="patient_portal",
        operation="portal_enroll",
    )


def policy_snapshot(db: DBSession, *, tenant_id: uuid.UUID) -> dict[str, Any]:
    """Diagnostics for entitlement summary — no PHI."""
    sub = _subscription(db, tenant_id=tenant_id)
    status = sub.status if sub else None
    return {
        "subscription_status": status,
        "capacity_expand_allowed": status in CAPACITY_EXPAND_STATUSES if status else False,
        "business_create_allowed": status in BUSINESS_CREATE_STATUSES if status else False,
        "patient_portal_access_ignores_commercial": True,
        "enforced_features": sorted(ENFORCED_FEATURES),
        "features": resolve_features(db, tenant_id=tenant_id),
    }
