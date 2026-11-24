"""Patient schemas. Identity / CRM contact fields only — no clinical payload."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, field_serializer

from app.platform.time import to_api_utc


class PatientCreateRequest(BaseModel):
    display_name: str = Field(min_length=2, max_length=200)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=320)
    date_of_birth: date | None = None
    emergency_contact_name: str | None = Field(default=None, max_length=200)
    emergency_contact_phone: str | None = Field(default=None, max_length=32)


class PatientUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=200)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=320)
    date_of_birth: date | None = None
    emergency_contact_name: str | None = Field(default=None, max_length=200)
    emergency_contact_phone: str | None = Field(default=None, max_length=32)
    is_active: bool | None = None


class PatientResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    display_name: str
    phone: str | None
    email: str | None = None
    date_of_birth: date | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None
    is_active: bool
    potential_duplicates: list[uuid.UUID] = []


class PatientImportRow(BaseModel):
    display_name: str = Field(min_length=2, max_length=200)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=320)
    date_of_birth: date | None = None
    emergency_contact_name: str | None = Field(default=None, max_length=200)
    emergency_contact_phone: str | None = Field(default=None, max_length=32)


class PatientImportRequest(BaseModel):
    rows: list[PatientImportRow] = Field(min_length=1, max_length=500)


class PatientImportResultRow(BaseModel):
    row: int
    status: str  # created | skipped_duplicate | error
    patient_id: uuid.UUID | None = None
    message: str | None = None


class PatientImportResponse(BaseModel):
    created: int
    skipped: int
    errors: int
    results: list[PatientImportResultRow]


class PatientOverviewResponse(BaseModel):
    patient_id: uuid.UUID
    display_name: str
    phone: str | None
    email: str | None
    date_of_birth: date | None
    is_active: bool
    last_visit_at: datetime | None
    next_appointment_at: datetime | None
    next_appointment_id: uuid.UUID | None
    outstanding_balance: str
    currency: str
    follow_up_due: date | None
    open_followups: int = 0
    overdue_followups: int = 0
    completed_followups: int = 0

    @field_serializer("last_visit_at", "next_appointment_at")
    def _ser_overview_ts(self, value: datetime | None) -> str | None:
        return None if value is None else to_api_utc(value)


class TimelineItemResponse(BaseModel):
    event_id: str
    kind: str
    category: str
    occurred_at: datetime
    title: str
    summary: str | None = None
    resource_type: str
    resource_id: uuid.UUID
    location_id: uuid.UUID | None = None
    status: str | None = None
    href: str | None = None

    @field_serializer("occurred_at")
    def _ser_occurred(self, value: datetime) -> str:
        return to_api_utc(value)


class TimelinePageResponse(BaseModel):
    items: list[TimelineItemResponse]
    next_cursor: str | None = None
