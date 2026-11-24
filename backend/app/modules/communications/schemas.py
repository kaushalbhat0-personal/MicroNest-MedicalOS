"""API schemas for follow-ups, communication consent, and logs."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_serializer

from app.platform.time import to_api_utc


class FollowUpCreateRequest(BaseModel):
    patient_id: uuid.UUID
    location_id: uuid.UUID
    due_at: datetime
    category: str
    reason: str = Field(min_length=2, max_length=200)
    source_type: str = "manual"
    source_id: uuid.UUID | None = None
    priority: str = "normal"
    assigned_user_id: uuid.UUID | None = None
    next_action: str | None = Field(default=None, max_length=200)


class FollowUpTransitionRequest(BaseModel):
    status: str
    outcome: str | None = Field(default=None, max_length=64)
    next_action: str | None = Field(default=None, max_length=200)
    next_due_at: datetime | None = None
    snooze_until: datetime | None = None
    assigned_user_id: uuid.UUID | None = None


class FollowUpAssignRequest(BaseModel):
    assigned_user_id: uuid.UUID | None = None


class FollowUpResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    patient_id: uuid.UUID
    location_id: uuid.UUID
    assigned_user_id: uuid.UUID | None
    due_at: datetime
    category: str
    reason: str
    source_type: str
    source_id: uuid.UUID | None
    priority: str
    status: str
    outcome: str | None
    next_action: str | None
    next_due_at: datetime | None
    snooze_until: datetime | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

    @field_serializer(
        "due_at",
        "next_due_at",
        "snooze_until",
        "created_at",
        "updated_at",
        "completed_at",
    )
    def _ser_ts(self, value: datetime | None) -> str | None:
        return None if value is None else to_api_utc(value)


class ConsentRecordRequest(BaseModel):
    patient_id: uuid.UUID
    channel: str
    purpose: str
    status: str  # granted | denied
    capture_source: str = "staff"


class ConsentRevokeRequest(BaseModel):
    patient_id: uuid.UUID
    channel: str
    purpose: str


class ConsentResponse(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    channel: str
    purpose: str
    status: str
    capture_source: str
    captured_at: datetime
    revoked_at: datetime | None
    is_current: bool

    @field_serializer("captured_at", "revoked_at")
    def _ser_ts(self, value: datetime | None) -> str | None:
        return None if value is None else to_api_utc(value)


class ConsentEligibilityResponse(BaseModel):
    patient_id: uuid.UUID
    channel: str
    purpose: str
    status: str  # unknown | granted | denied | revoked
    eligible: bool


class CommunicationLogCreateRequest(BaseModel):
    patient_id: uuid.UUID
    channel: str
    purpose: str
    outcome: str
    location_id: uuid.UUID | None = None
    follow_up_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=280)
    occurred_at: datetime | None = None


class CommunicationLogResponse(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    location_id: uuid.UUID | None
    follow_up_id: uuid.UUID | None
    channel: str
    purpose: str
    outcome: str
    staff_user_id: uuid.UUID
    occurred_at: datetime
    note: str | None

    @field_serializer("occurred_at")
    def _ser_ts(self, value: datetime) -> str:
        return to_api_utc(value)


class WhatsAppLinkRequest(BaseModel):
    patient_id: uuid.UUID
    purpose: str
    message: str | None = Field(default=None, max_length=500)
    require_consent: bool = True


class WhatsAppLinkResponse(BaseModel):
    url: str
    patient_id: uuid.UUID
    patient_display_name: str
    purpose: str
    consent_status: str
    eligible: bool
    auto_send: bool = False
    delivery_tracked: bool = False
