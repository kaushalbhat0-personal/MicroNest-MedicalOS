"""P2.1 entitlement shadow evaluation — read-only, never enforces.

Resolves tenant subscription + immutable plan revision, measures supported
usage, and returns hypothetical decisions. Authorization (require/permission)
remains a separate axis and stays authoritative for actual requests.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.modules.clinics.models import Location
from app.modules.identity.models import Practitioner
from app.modules.subscriptions.models import Subscription, SubscriptionPlan
from app.modules.tenancy.models import Membership, Role, Verification
from app.platform.time import UTC
from app.platform.time import now as utcnow

log = logging.getLogger("healthcare_os.entitlements")

EVAL_MODE = "shadow"

# --- Result codes (shadow decisions) ---
ALLOWED = "allowed"
WOULD_EXCEED_LIMIT = "would_exceed_limit"
FEATURE_NOT_INCLUDED = "feature_not_included"
SUBSCRIPTION_INACTIVE = "subscription_inactive"
UNAVAILABLE = "unavailable"
UNKNOWN = "unknown"

# Numeric limits with clear plan columns + measurable usage.
LIMIT_KEYS = frozenset({"max_staff_seats", "max_locations", "max_practitioners"})

# Boolean feature keys recognized in plan.features JSONB.
FEATURE_KEYS = frozenset(
    {
        "patient_portal",
        "inventory",
        "operations_dashboard",
        "clinic_billing",
        "staff_workforce",
    }
)

# Documented candidates that are not measurable / not on plans yet.
UNSUPPORTED_KEYS = frozenset(
    {
        "max_monthly_appointments",
        "max_storage_bytes",
        "advanced_reports",
        "custom_branding",
    }
)

# Commercial statuses that remain entitled for shadow "would allow" purposes.
# past_due / grace still entitled (write gates deferred to P2.2/P2.3).
COMMERCIALLY_USABLE = frozenset({"trial", "active", "past_due", "grace"})
COMMERCIALLY_INACTIVE = frozenset({"suspended", "cancelled", "expired"})


def _as_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, int | float) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1", "yes"):
            return True
        if lowered in ("false", "0", "no", ""):
            return False
    return None  # malformed


def parse_features(raw: object) -> dict[str, bool]:
    """Normalize plan.features to known boolean keys; ignore unknown keys."""
    out: dict[str, bool] = {k: False for k in FEATURE_KEYS}
    if not isinstance(raw, dict):
        return out
    for key in FEATURE_KEYS:
        if key not in raw:
            continue
        parsed = _as_bool(raw[key])
        if parsed is None:
            continue
        out[key] = parsed
    return out


def count_staff_seats(db: DBSession, *, tenant_id: uuid.UUID) -> int:
    """Active memberships excluding the seed ``patient`` role.

    Inactive memberships do not count. Practitioners without a membership
    do not count toward seats. Pending invitation reservations are counted
    separately via ``enforcement.count_pending_staff_invite_reservations``
    and included in consumed capacity for P2.2 enforcement.
    """
    return int(
        db.execute(
            select(func.count())
            .select_from(Membership)
            .join(Role, Role.id == Membership.role_id)
            .where(
                Membership.tenant_id == tenant_id,
                Membership.is_active.is_(True),
                Role.name != "patient",
            )
        ).scalar_one()
    )


def count_active_locations(db: DBSession, *, tenant_id: uuid.UUID) -> int:
    """Active locations for the tenant (``locations.is_active``)."""
    return int(
        db.execute(
            select(func.count())
            .select_from(Location)
            .where(Location.tenant_id == tenant_id, Location.is_active.is_(True))
        ).scalar_one()
    )


def count_approved_practitioners(db: DBSession, *, tenant_id: uuid.UUID) -> int:
    """Active practitioners with an approved verification for this tenant.

    Distinct from staff seats (memberships). Visiting/unverified practitioners
    do not count.
    """
    return int(
        db.execute(
            select(func.count())
            .select_from(Verification)
            .join(Practitioner, Practitioner.id == Verification.practitioner_id)
            .where(
                Verification.tenant_id == tenant_id,
                Verification.status == "approved",
                Practitioner.is_active.is_(True),
            )
        ).scalar_one()
    )


def measure_usage(db: DBSession, *, tenant_id: uuid.UUID) -> dict[str, dict[str, Any]]:
    """Return usage map: key → {available, value?, definition}.

    ``max_staff_seats.value`` is **consumed** capacity (active seats + pending
    unexpired non-patient invitation reservations). Breakdown fields are
    included for UI/diagnostics.
    """
    # Local import avoids circular import at module load (enforcement → entitlements).
    from app.modules.subscriptions import enforcement as enf

    measured_at = utcnow()
    seats = count_staff_seats(db, tenant_id=tenant_id)
    reserved = enf.count_pending_staff_invite_reservations(db, tenant_id=tenant_id)
    return {
        "max_staff_seats": {
            "available": True,
            "value": seats + reserved,
            "active_memberships": seats,
            "pending_reservations": reserved,
            "definition": (
                "Active non-patient memberships + pending unexpired non-patient "
                "invitation reservations. Soft-expired pending invites do not reserve."
            ),
            "measured_at": measured_at,
        },
        "max_locations": {
            "available": True,
            "value": count_active_locations(db, tenant_id=tenant_id),
            "definition": "COUNT locations where is_active is true.",
            "measured_at": measured_at,
        },
        "max_practitioners": {
            "available": True,
            "value": count_approved_practitioners(db, tenant_id=tenant_id),
            "definition": (
                "COUNT practitioners with approved verification for the tenant "
                "and practitioner.is_active. One count per practitioner (not per location)."
            ),
            "measured_at": measured_at,
        },
        "max_monthly_appointments": {
            "available": False,
            "value": None,
            "definition": (
                "No plan entitlement column or commercial period quota defined; "
                "appointments exist but are not a plan limit."
            ),
            "measured_at": measured_at,
        },
        "max_storage_bytes": {
            "available": False,
            "value": None,
            "definition": (
                "Document size_bytes is optional and not a complete tenant "
                "storage ledger; measurement unavailable."
            ),
            "measured_at": measured_at,
        },
    }


def _subscription_commercially_usable(status: str | None) -> bool | None:
    if status is None:
        return None
    if status in COMMERCIALLY_USABLE:
        return True
    if status in COMMERCIALLY_INACTIVE:
        return False
    return None


def _shadow_decision(
    *,
    key: str,
    result: str,
    effective_value: object,
    usage: object | None,
    limit: object | None,
    reason_code: str,
    would_deny_if_enforced: bool,
    measured_at: datetime | None = None,
    evaluation_mode: str | None = None,
) -> dict[str, Any]:
    from app.modules.subscriptions.commercial_policy import ENFORCED_FEATURES

    base_key = key.removesuffix("__increment")
    mode = evaluation_mode or (
        "enforced"
        if base_key in LIMIT_KEYS or base_key in ENFORCED_FEATURES
        else EVAL_MODE
    )
    return {
        "key": key,
        "result": result,
        "effective_value": effective_value,
        "usage": usage,
        "limit": limit,
        "reason_code": reason_code,
        "evaluation_mode": mode,
        "would_deny_if_enforced": would_deny_if_enforced,
        "measured_at": measured_at or utcnow(),
    }


def evaluate_feature(
    *,
    key: str,
    features: dict[str, bool],
    commercial_usable: bool | None,
) -> dict[str, Any]:
    if key in UNSUPPORTED_KEYS:
        return _shadow_decision(
            key=key,
            result=UNAVAILABLE,
            effective_value=None,
            usage=None,
            limit=None,
            reason_code="unsupported_entitlement",
            would_deny_if_enforced=False,
        )
    if key not in FEATURE_KEYS:
        return _shadow_decision(
            key=key,
            result=UNKNOWN,
            effective_value=None,
            usage=None,
            limit=None,
            reason_code="unknown_entitlement_key",
            would_deny_if_enforced=False,
        )
    if commercial_usable is None:
        return _shadow_decision(
            key=key,
            result=UNKNOWN,
            effective_value=False,
            usage=None,
            limit=None,
            reason_code="subscription_unresolved",
            would_deny_if_enforced=True,
        )
    if commercial_usable is False:
        return _shadow_decision(
            key=key,
            result=SUBSCRIPTION_INACTIVE,
            effective_value=False,
            usage=None,
            limit=None,
            reason_code="subscription_not_commercially_usable",
            would_deny_if_enforced=True,
        )
    included = bool(features.get(key, False))
    if not included:
        return _shadow_decision(
            key=key,
            result=FEATURE_NOT_INCLUDED,
            effective_value=False,
            usage=None,
            limit=None,
            reason_code="feature_false_or_absent_on_plan",
            would_deny_if_enforced=True,
        )
    return _shadow_decision(
        key=key,
        result=ALLOWED,
        effective_value=True,
        usage=None,
        limit=None,
        reason_code="feature_included",
        would_deny_if_enforced=False,
    )


def evaluate_limit(
    *,
    key: str,
    limit_value: int | None,
    usage_entry: dict[str, Any] | None,
    commercial_usable: bool | None,
    proposed_additional: int = 0,
) -> dict[str, Any]:
    if key in UNSUPPORTED_KEYS or (
        usage_entry is not None and usage_entry.get("available") is False
    ):
        return _shadow_decision(
            key=key,
            result=UNAVAILABLE,
            effective_value=None,
            usage=None,
            limit=limit_value,
            reason_code="usage_unavailable",
            would_deny_if_enforced=False,
            measured_at=(usage_entry or {}).get("measured_at"),
        )
    if key not in LIMIT_KEYS:
        return _shadow_decision(
            key=key,
            result=UNKNOWN,
            effective_value=None,
            usage=None,
            limit=limit_value,
            reason_code="unknown_entitlement_key",
            would_deny_if_enforced=False,
        )
    if commercial_usable is None:
        return _shadow_decision(
            key=key,
            result=UNKNOWN,
            effective_value=None,
            usage=(usage_entry or {}).get("value"),
            limit=limit_value,
            reason_code="subscription_unresolved",
            would_deny_if_enforced=True,
            measured_at=(usage_entry or {}).get("measured_at"),
        )
    if commercial_usable is False:
        return _shadow_decision(
            key=key,
            result=SUBSCRIPTION_INACTIVE,
            effective_value=None,
            usage=(usage_entry or {}).get("value"),
            limit=limit_value,
            reason_code="subscription_not_commercially_usable",
            would_deny_if_enforced=True,
            measured_at=(usage_entry or {}).get("measured_at"),
        )
    if limit_value is None:
        return _shadow_decision(
            key=key,
            result=UNKNOWN,
            effective_value=None,
            usage=(usage_entry or {}).get("value"),
            limit=None,
            reason_code="limit_missing_on_plan",
            would_deny_if_enforced=True,
            measured_at=(usage_entry or {}).get("measured_at"),
        )
    usage_val = int((usage_entry or {}).get("value") or 0)
    projected = usage_val + max(proposed_additional, 0)
    if projected > limit_value:
        return _shadow_decision(
            key=key,
            result=WOULD_EXCEED_LIMIT,
            effective_value=limit_value,
            usage=usage_val,
            limit=limit_value,
            reason_code="projected_usage_exceeds_limit",
            would_deny_if_enforced=True,
            measured_at=(usage_entry or {}).get("measured_at"),
        )
    return _shadow_decision(
        key=key,
        result=ALLOWED,
        effective_value=limit_value,
        usage=usage_val,
        limit=limit_value,
        reason_code="within_limit",
        would_deny_if_enforced=False,
        measured_at=(usage_entry or {}).get("measured_at"),
    )


def resolve_entitlements(db: DBSession, *, tenant_id: uuid.UUID) -> dict[str, Any]:
    """Central resolver. Never mutates. Never trusts client ownership."""
    measured_at = utcnow()
    sub = db.execute(
        select(Subscription).where(Subscription.tenant_id == tenant_id)
    ).scalar_one_or_none()

    plan: SubscriptionPlan | None = None
    if sub is not None:
        plan = db.get(SubscriptionPlan, sub.plan_id)

    usage = measure_usage(db, tenant_id=tenant_id)
    features = parse_features(plan.features if plan is not None else {})
    commercial = _subscription_commercially_usable(sub.status if sub else None)

    resolution: dict[str, Any] = {
        "tenant_id": tenant_id,
        # Mixed mode: numeric limits below are enforced; features remain shadow.
        "evaluation_mode": "enforced",
        "enforcement_active": True,
        "enforced_keys": sorted(LIMIT_KEYS),
        "shadow_only_keys": sorted(UNSUPPORTED_KEYS),
        "resolved_at": measured_at,
        "subscription": None,
        "plan": None,
        "resolution_notes": [],
        "features": features,
        "limits": {},
        "usage": usage,
        "evaluations": [],
        "authorization_note": (
            "Plan features do not grant user permissions. User permissions do "
            "not grant plan features. Existing require(permission) remains "
            "authoritative for API access. Numeric capacity and catalog "
            "features are enforced per commercial_policy. Patient portal "
            "access is independent of commercial delinquency; abuse "
            "suspension (tenants.status) remains separate."
        ),
    }

    if sub is None:
        resolution["resolution_notes"].append("missing_subscription")
        commercial = None
    else:
        trial_ends = sub.trial_ends_at
        if trial_ends is not None and trial_ends.tzinfo is None:
            trial_ends = trial_ends.replace(tzinfo=UTC)
        is_in_trial = sub.status == "trial" and (
            trial_ends is None or trial_ends >= measured_at
        )
        resolution["subscription"] = {
            "id": sub.id,
            "status": sub.status,
            "trial_ends_at": sub.trial_ends_at,
            "period_start": sub.period_start,
            "period_end": sub.period_end,
            "grace_ends_at": sub.grace_ends_at,
            "cancelled_at": sub.cancelled_at,
            "is_in_trial": is_in_trial,
            "commercially_usable": commercial,
        }

    if plan is None:
        if sub is not None:
            resolution["resolution_notes"].append("missing_plan_revision")
            commercial = None
    else:
        if not plan.is_active:
            resolution["resolution_notes"].append("plan_revision_inactive_in_catalog")
        resolution["plan"] = {
            "id": plan.id,
            "code": plan.code,
            "family_code": plan.family_code,
            "version": plan.version,
            "name": plan.name,
            "is_active": plan.is_active,
        }
        resolution["limits"] = {
            "max_staff_seats": plan.max_staff_seats,
            "max_locations": plan.max_locations,
            "max_practitioners": plan.max_practitioners,
        }

    evaluations: list[dict[str, Any]] = []
    for key in sorted(FEATURE_KEYS):
        evaluations.append(
            evaluate_feature(
                key=key, features=features, commercial_usable=commercial
            )
        )
    for key in sorted(LIMIT_KEYS):
        evaluations.append(
            evaluate_limit(
                key=key,
                limit_value=resolution["limits"].get(key) if resolution["limits"] else None,
                usage_entry=usage.get(key),
                commercial_usable=commercial,
                proposed_additional=0,
            )
        )
        # Also report "would one more exceed?" for diagnostics.
        one_more = evaluate_limit(
            key=key,
            limit_value=resolution["limits"].get(key) if resolution["limits"] else None,
            usage_entry=usage.get(key),
            commercial_usable=commercial,
            proposed_additional=1,
        )
        one_more = {**one_more, "key": f"{key}__increment", "probe": "create_one"}
        evaluations.append(one_more)

    for key in sorted(UNSUPPORTED_KEYS):
        if key.startswith("max_"):
            evaluations.append(
                evaluate_limit(
                    key=key,
                    limit_value=None,
                    usage_entry=usage.get(key)
                    or {
                        "available": False,
                        "value": None,
                        "measured_at": measured_at,
                    },
                    commercial_usable=commercial,
                )
            )
        else:
            evaluations.append(
                evaluate_feature(
                    key=key, features=features, commercial_usable=commercial
                )
            )

    resolution["evaluations"] = evaluations

    from app.modules.subscriptions import commercial_policy as cpol

    resolution["commercial_policy"] = cpol.policy_snapshot(db, tenant_id=tenant_id)
    resolution["enforced_keys"] = sorted(LIMIT_KEYS | cpol.ENFORCED_FEATURES)
    resolution["shadow_only_keys"] = sorted(UNSUPPORTED_KEYS)

    # Structured observability — no patient/clinical fields.
    log.info(
        "entitlement_shadow_resolved tenant_id=%s status=%s plan=%s v=%s notes=%s",
        str(tenant_id),
        sub.status if sub else None,
        plan.code if plan else None,
        plan.version if plan else None,
        ",".join(resolution["resolution_notes"]) or "-",
    )
    return resolution
