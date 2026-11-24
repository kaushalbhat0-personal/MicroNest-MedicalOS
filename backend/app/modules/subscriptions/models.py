"""Subscription foundation: plan catalog + per-tenant subscription.

P2.0 extends the O1.2a trial tables in place (no duplicate Plan/TenantSubscription
entities). Plans are immutable revisions identified by (family_code, version);
subscriptions remain one current row per tenant with append-only events.

Billing separation (hard invariant): this module never imports clinic
billing or clinical modules; billing modules never import this module.
The ledgers join by tenant_id only. No payment provider in this module.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db import Base

TRIAL_PLAN_CODE = "trial-14d"
TRIAL_FAMILY = "trial-14d"
TRIAL_STATUS = "trial"

# Established status vocabulary (do not rename to "trialing" / "grace_period").
SUBSCRIPTION_STATUSES = frozenset(
    {"trial", "active", "past_due", "grace", "suspended", "cancelled", "expired"}
)

TERMINAL_STATUSES = frozenset({"cancelled", "expired"})

# Manual transitions allowed in P2.0 (admin/platform). Webhook-driven paths
# (past_due ← provider failure, renewals) are reserved for P2.4+.
STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    "trial": frozenset({"active", "expired", "cancelled", "suspended"}),
    "active": frozenset({"past_due", "cancelled", "suspended", "grace"}),
    "past_due": frozenset({"active", "grace", "suspended", "cancelled"}),
    "grace": frozenset({"active", "suspended", "cancelled", "expired"}),
    "suspended": frozenset({"active", "cancelled", "expired"}),
    "cancelled": frozenset(),
    "expired": frozenset({"trial", "active"}),  # re-open only via authorized assign
}

EVENT_CREATED = "created"
EVENT_STATUS = "status_transition"
EVENT_PLAN = "plan_assigned"
EVENT_TRIAL_EXT = "trial_extended"
EVENT_TYPES = frozenset({EVENT_CREATED, EVENT_STATUS, EVENT_PLAN, EVENT_TRIAL_EXT})

BILLING_INTERVALS = frozenset({"month", "year"})


class SubscriptionPlan(Base):
    """Immutable plan revision. Catalog changes create a new row (version+1).

    ``code`` remains globally unique (e.g. starter-v1). ``family_code`` is the
    stable product slug; ``version`` is the revision within the family.
    Writable only via migration/owner/platform service — never client body.
    """

    __tablename__ = "subscription_plans"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    family_code: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    currency: Mapped[str] = mapped_column(Text, nullable=False, default="INR")
    billing_interval: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    features: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    max_locations: Mapped[int] = mapped_column(Integer, nullable=False)
    max_practitioners: Mapped[int] = mapped_column(Integer, nullable=False)
    max_staff_seats: Mapped[int] = mapped_column(Integer, nullable=False)
    trial_days: Mapped[int] = mapped_column(Integer, nullable=False, default=14)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("family_code", "version", name="uq_subscription_plans_family_version"),
        Index("ix_subscription_plans_family", "family_code"),
        CheckConstraint(
            "billing_interval IS NULL OR billing_interval IN ('month', 'year')",
            name="ck_plan_billing_interval",
        ),
        CheckConstraint("currency = 'INR'", name="ck_plan_currency"),
        CheckConstraint("price_minor >= 0", name="ck_plan_price_minor"),
        CheckConstraint("version >= 1", name="ck_plan_version_positive"),
    )


class Subscription(Base):
    """Current per-tenant subscription. Exactly one row per tenant."""

    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("subscription_plans.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=TRIAL_STATUS)
    trial_ends_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    period_start: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    grace_ends_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # P2.5: owner requested cancel; access continues until period_end.
    cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    # Reserved for future payment-provider customer/subscription ids. Unused in P2.0.
    provider_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (UniqueConstraint("tenant_id", name="uq_subscriptions_tenant"),)


class SubscriptionEvent(Base):
    """Append-only commercial history for a tenant subscription."""

    __tablename__ = "subscription_events"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    from_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    to_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    from_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("subscription_plans.id", ondelete="SET NULL"),
        nullable=True,
    )
    to_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("subscription_plans.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_subscription_events_tenant_created", "tenant_id", "created_at"),
        CheckConstraint(
            "event_type IN ('created','status_transition','plan_assigned','trial_extended')",
            name="ck_sub_event_type",
        ),
    )
