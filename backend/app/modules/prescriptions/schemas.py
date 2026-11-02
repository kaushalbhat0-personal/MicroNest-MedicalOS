"""Prescription schemas. Shape only; signing/correction rules live in the
service. Instructions are clinical content: never logged, never audited."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PrescriptionItemRequest(BaseModel):
    medication_code: str = Field(max_length=40)
    dose: str = Field(min_length=1, max_length=64)
    route: str = Field(min_length=1, max_length=32)
    frequency: str = Field(min_length=1, max_length=64)
    duration_days: int | None = Field(default=None, ge=1, le=365)
    quantity: float | None = Field(default=None, ge=0)
    instructions: str = Field(min_length=1, max_length=2000)


class PrescriptionCreateRequest(BaseModel):
    items: list[PrescriptionItemRequest] = Field(min_length=1, max_length=50)


class PrescriptionCancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=200)


class PrescriptionItemResponse(BaseModel):
    id: uuid.UUID
    medication_code: str
    medication_name: str
    line_no: int
    dose: str
    route: str
    frequency: str
    duration_days: int | None
    quantity: float | None
    instructions: str


class PrescriptionResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    encounter_id: uuid.UUID
    prescribed_by: uuid.UUID
    status: str
    version: int
    supersedes_id: uuid.UUID | None
    superseded_by_id: uuid.UUID | None
    signed_by: uuid.UUID | None
    signed_at: datetime | None
    cancelled_by: uuid.UUID | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    items: list[PrescriptionItemResponse]
    created_at: datetime
    updated_at: datetime


class MedicationResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    generic_name: str | None
    strength: str | None
    dosage_form: str | None
    atc: str | None
    is_active: bool
