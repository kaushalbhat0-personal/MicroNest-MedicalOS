"""Scheduling schemas. Thin validation at the boundary; domain rules
(overlap, lifecycle, scope) live in the service."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, field_serializer

from app.platform.time import to_api_utc


class AppointmentCreateRequest(BaseModel):
    patient_id: uuid.UUID
    practitioner_id: uuid.UUID
    location_id: uuid.UUID
    # ISO-8601. Aware values are instants; naive values are wall-clock in
    # `timezone` (default: the location's timezone).
    start: datetime
    duration_minutes: int = Field(ge=5, le=480)
    notes: str | None = Field(default=None, max_length=500)
    timezone: str | None = Field(default=None, max_length=64)
    idempotency_key: str | None = Field(default=None, max_length=64)
    # Walk-in: allow start at/near now and auto-check-in after create.
    walk_in: bool = False


class AvailabilitySlot(BaseModel):
    start_at: datetime
    end_at: datetime


class AvailabilityResponse(BaseModel):
    practitioner_id: uuid.UUID
    location_id: uuid.UUID
    timezone: str
    date: str
    slot_minutes: int
    slots: list[AvailabilitySlot]


class AppointmentRescheduleRequest(BaseModel):
    start: datetime
    duration_minutes: int = Field(ge=5, le=480)


class AppointmentStatusRequest(BaseModel):
    status: str = Field(pattern=r"^(scheduled|confirmed|checked_in|completed|cancelled|no_show)$")


class AppointmentCancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=200)


class AppointmentResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    patient_id: uuid.UUID
    practitioner_id: uuid.UUID
    location_id: uuid.UUID
    start_at: datetime
    end_at: datetime
    timezone: str
    status: str
    notes: str | None
    queue_token: int | None = None
    queue_date: date | None = None
    cancelled_at: datetime | None
    cancelled_by: uuid.UUID | None
    cancel_reason: str | None
    created_at: datetime
    updated_at: datetime

    @field_serializer("start_at", "end_at", "created_at", "updated_at", "cancelled_at")
    def _serialize_instants(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return to_api_utc(value)


class AppointmentListResponse(BaseModel):
    items: list[AppointmentResponse]
    # Keyset cursor: pass back as `cursor` to fetch the next page. Null = end.
    next_cursor: uuid.UUID | None


class ReceptionQueueResponse(BaseModel):
    """Location-scoped daily reception board (refs + status + token only)."""

    location_id: uuid.UUID
    queue_date: date
    timezone: str
    waiting: list[AppointmentResponse]
    checked_in: list[AppointmentResponse]
    completed: list[AppointmentResponse]
    no_show: list[AppointmentResponse]
    cancelled: list[AppointmentResponse]
