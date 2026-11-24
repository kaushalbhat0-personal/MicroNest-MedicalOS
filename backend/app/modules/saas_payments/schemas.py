"""API schemas for SaaS checkout / payments (no secrets)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CheckoutRequest(BaseModel):
    plan_code: str = Field(min_length=2, max_length=64)
    idempotency_key: str = Field(min_length=8, max_length=128)
    purpose: str = Field(default="checkout", pattern="^(checkout|renewal)$")


class CancelRequest(BaseModel):
    reason: str = Field(min_length=2, max_length=500)
    at_period_end: bool = False


class CheckoutHint(BaseModel):
    provider: str
    order_id: str
    amount_minor: int
    currency: str
    public_key: str | None = None
    hint: dict[str, Any] = Field(default_factory=dict)
    return_url_informational: bool = True


class SaasPaymentTransactionResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    status: str
    amount_minor: int
    currency: str
    billing_interval: str | None = None
    plan_code: str | None = None
    plan_name: str | None = None
    provider: str
    provider_order_id: str | None = None
    paid_at: datetime | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None
    idempotency_key: str
    purpose: str = "checkout"
    refunded_amount_minor: int = 0
    created_at: datetime
    failure_reason: str | None = None
    checkout: CheckoutHint | None = None


class ReconcileResponse(BaseModel):
    tenant_id: uuid.UUID
    subscription_status: str | None
    paid_count: int
    pending_count: int
    refunded_count: int = 0
    findings: list[str]


class WebhookInboxItem(BaseModel):
    id: uuid.UUID
    provider: str
    provider_event_id: str
    event_type: str
    status: str
    attempts: int
    last_error: str | None = None
    tenant_id: uuid.UUID | None = None
    related_transaction_id: uuid.UUID | None = None
    received_at: datetime
    processed_at: datetime | None = None
    next_attempt_at: datetime | None = None
    event_refs: dict[str, Any] = Field(default_factory=dict)


class ProcessDueResponse(BaseModel):
    processed: int
    results: list[dict[str, Any]]
