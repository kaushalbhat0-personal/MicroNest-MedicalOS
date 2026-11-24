"""SaaS payment tables. Never join to patients/clinic AR tables."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
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

TXN_PENDING = "pending"
TXN_PAID = "paid"
TXN_FAILED = "failed"
TXN_PARTIAL_REFUND = "partially_refunded"
TXN_REFUNDED = "refunded"
TXN_CANCELLED = "cancelled"
TXN_DISPUTED = "disputed"
TXN_STATUSES = frozenset(
    {
        TXN_PENDING,
        TXN_PAID,
        TXN_FAILED,
        TXN_PARTIAL_REFUND,
        TXN_REFUNDED,
        TXN_CANCELLED,
        TXN_DISPUTED,
    }
)

# Durable inbox lifecycle (P2.5).
INBOX_RECEIVED = "received"
INBOX_VERIFIED = "verified"
INBOX_PENDING = "pending"
INBOX_PROCESSING = "processing"
INBOX_PROCESSED = "processed"
INBOX_RETRYABLE = "retryable_failure"
INBOX_PERMANENT = "permanent_failure"
INBOX_IGNORED = "ignored"
INBOX_DUPLICATE = "duplicate"

INBOX_RETRYABLE_STATUSES = frozenset({INBOX_PENDING, INBOX_RETRYABLE})
WEBHOOK_MAX_ATTEMPTS = 8


class SaasCustomer(Base):
    """Provider customer reference for a clinic tenant."""

    __tablename__ = "saas_customers"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_customer_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", name="uq_saas_customers_tenant_provider"),
        UniqueConstraint(
            "provider", "provider_customer_id", name="uq_saas_customers_provider_ref"
        ),
    )


class SaasPaymentTransaction(Base):
    """Internal SaaS charge attempt. Amount snapshotted from plan at checkout."""

    __tablename__ = "saas_payment_transactions"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("subscription_plans.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=TXN_PENDING)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    billing_interval: Mapped[str | None] = mapped_column(String(16), nullable=True)
    provider_order_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_payment_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False, default="checkout")
    period_start: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    refunded_amount_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_saas_txn_tenant_idempotency"
        ),
        Index("ix_saas_txn_tenant_created", "tenant_id", "created_at"),
        Index("ix_saas_txn_provider_order", "provider", "provider_order_id"),
        CheckConstraint(
            "status IN ('pending','paid','failed','partially_refunded','refunded',"
            "'cancelled','disputed')",
            name="ck_saas_txn_status",
        ),
        CheckConstraint("amount_minor >= 0", name="ck_saas_txn_amount"),
        CheckConstraint("currency = 'INR'", name="ck_saas_txn_currency"),
        CheckConstraint(
            "refunded_amount_minor >= 0 AND refunded_amount_minor <= amount_minor",
            name="ck_saas_txn_refunded_amount",
        ),
    )


class SaasWebhookInbox(Base):
    """Durable webhook receipt ledger (platform-scoped)."""

    __tablename__ = "saas_webhook_inbox"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=INBOX_PENDING)
    payload_digest: Mapped[str] = mapped_column(Text, nullable=False)
    # Safe refs only (order/payment ids, amounts). Never full card/PHI payloads.
    event_refs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    related_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("saas_payment_transactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    received_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_event_id", name="uq_saas_webhook_provider_event"
        ),
        Index("ix_saas_webhook_status", "status", "received_at"),
        Index("ix_saas_webhook_retry", "status", "next_attempt_at"),
        CheckConstraint(
            "status IN ('received','verified','pending','processing','processed',"
            "'retryable_failure','permanent_failure','ignored','duplicate')",
            name="ck_saas_webhook_status",
        ),
    )
