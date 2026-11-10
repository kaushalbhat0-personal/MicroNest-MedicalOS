"""Subscription foundation (O1.2a): trial catalog + per-tenant subscription.

Trial only: every provisioned workspace gets exactly one `subscriptions`
row (plan `trial-14d`, status `trial`, 14 days, no card, no charge, no
gateway). No expiry enforcement, no checkout, no platform billing tables in
this slice — those are explicitly deferred.

Billing separation (hard invariant): this module never imports clinic
billing or clinical modules (except shared `Money` pure functions in the
future); billing modules never import this module. The ledgers join by
tenant_id only.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db import Base

TRIAL_PLAN_CODE = "trial-14d"
TRIAL_STATUS = "trial"

SUBSCRIPTION_STATUSES = frozenset(
    {"trial", "active", "past_due", "grace", "suspended", "cancelled", "expired"}
)


class SubscriptionPlan(Base):
    """Versioned plan catalog (non-RLS readable catalog, like seed roles).

    Rows are seeded by migration and never edited in place — a plan change
    is a new row + migration. Writable in practice only via migration/owner.
    """

    __tablename__ = "subscription_plans"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    max_locations: Mapped[int] = mapped_column(Integer, nullable=False)
    max_practitioners: Mapped[int] = mapped_column(Integer, nullable=False)
    max_staff_seats: Mapped[int] = mapped_column(Integer, nullable=False)
    trial_days: Mapped[int] = mapped_column(Integer, nullable=False, default=14)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class Subscription(Base):
    """Per-tenant subscription. Exactly one row per tenant (UNIQUE tenant)."""

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
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (UniqueConstraint("tenant_id", name="uq_subscriptions_tenant"),)
