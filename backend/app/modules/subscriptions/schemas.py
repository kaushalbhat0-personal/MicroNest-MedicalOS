"""P2.0 commercial plan + subscription API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PlanLimitsView(BaseModel):
    max_locations: int
    max_practitioners: int
    max_staff_seats: int
    enforced: bool = True


class PlanResponse(BaseModel):
    id: uuid.UUID
    code: str
    family_code: str
    version: int
    name: str
    description: str
    currency: str
    billing_interval: str | None
    price_minor: int
    features: dict[str, Any]
    limits: PlanLimitsView
    trial_days: int
    is_active: bool
    created_at: datetime


class SubscriptionDetailResponse(BaseModel):
    """Current tenant subscription. Limits are informational only."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    status: str
    plan: PlanResponse
    trial_starts_at: datetime | None = None
    trial_ends_at: datetime | None = None
    is_in_trial: bool = False
    period_start: datetime | None = None
    period_end: datetime | None = None
    grace_ends_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancel_reason: str | None = None
    cancel_at_period_end: bool = False
    provider_ref: str | None = None
    limits_enforced: bool = True
    created_at: datetime
    updated_at: datetime


class SubscriptionEventResponse(BaseModel):
    id: uuid.UUID
    event_type: str
    from_status: str | None
    to_status: str | None
    from_plan_id: uuid.UUID | None
    to_plan_id: uuid.UUID | None
    actor_id: uuid.UUID | None
    note: str | None
    created_at: datetime


class AssignPlanRequest(BaseModel):
    plan_code: str = Field(min_length=2, max_length=120)
    note: str | None = Field(default=None, max_length=500)
    # When assigning a paid plan, optionally move status (default keeps current
    # unless trial→active for non-trial plans).
    target_status: str | None = Field(default=None, max_length=20)


class TransitionStatusRequest(BaseModel):
    status: str = Field(min_length=2, max_length=20)
    note: str | None = Field(default=None, max_length=500)
    cancel_reason: str | None = Field(default=None, max_length=500)
    grace_ends_at: datetime | None = None


class ExtendTrialRequest(BaseModel):
    days: int = Field(ge=1, le=90)
    note: str | None = Field(default=None, max_length=500)


class EntitlementUsageEntry(BaseModel):
    available: bool
    value: int | None = None
    definition: str
    measured_at: datetime
    active_memberships: int | None = None
    pending_reservations: int | None = None


class ShadowEvaluation(BaseModel):
    key: str
    result: str
    effective_value: Any | None = None
    usage: int | None = None
    limit: int | None = None
    reason_code: str
    evaluation_mode: str = "shadow"
    would_deny_if_enforced: bool
    measured_at: datetime
    probe: str | None = None


class EntitlementSubscriptionInfo(BaseModel):
    id: uuid.UUID
    status: str
    trial_ends_at: datetime | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None
    grace_ends_at: datetime | None = None
    cancelled_at: datetime | None = None
    is_in_trial: bool = False
    commercially_usable: bool | None = None


class EntitlementPlanInfo(BaseModel):
    id: uuid.UUID
    code: str
    family_code: str
    version: int
    name: str
    is_active: bool


class EntitlementSummaryResponse(BaseModel):
    tenant_id: uuid.UUID
    evaluation_mode: str
    enforcement_active: bool
    enforced_keys: list[str] = Field(default_factory=list)
    shadow_only_keys: list[str] = Field(default_factory=list)
    resolved_at: datetime
    subscription: EntitlementSubscriptionInfo | None = None
    plan: EntitlementPlanInfo | None = None
    resolution_notes: list[str] = Field(default_factory=list)
    features: dict[str, bool] = Field(default_factory=dict)
    limits: dict[str, int] = Field(default_factory=dict)
    usage: dict[str, EntitlementUsageEntry] = Field(default_factory=dict)
    evaluations: list[ShadowEvaluation] = Field(default_factory=list)
    authorization_note: str
    commercial_policy: dict[str, Any] = Field(default_factory=dict)
