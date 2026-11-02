"""Dental schemas. Shape only; FDI/surface validation and lifecycles live in
the service. No money fields exist at this layer."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class DentalConditionResponse(BaseModel):
    id: uuid.UUID
    code: str
    display: str
    is_active: bool


class FindingCreateRequest(BaseModel):
    tooth: int
    condition_code: str = Field(max_length=40)
    surfaces: list[str] = Field(default_factory=list, max_length=8)
    details: str | None = Field(default=None, max_length=500)


class FindingResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    encounter_id: uuid.UUID
    practitioner_id: uuid.UUID
    tooth: int
    condition_code: str
    condition_display: str
    surfaces: list[str]
    status: str
    details: str | None
    created_at: datetime
    updated_at: datetime


class DentalProcedureResponse(BaseModel):
    id: uuid.UUID
    code: str
    display: str
    description: str | None
    specialty: str
    external_code: str | None
    is_active: bool


class PlanItemRequest(BaseModel):
    procedure_code: str = Field(max_length=40)
    tooth: int | None = None
    surface: str | None = Field(default=None, max_length=16)
    sequence: int = Field(default=1, ge=1, le=100)
    notes: str | None = Field(default=None, max_length=500)


class PlanCreateRequest(BaseModel):
    patient_id: uuid.UUID
    encounter_id: uuid.UUID | None = None
    practitioner_id: uuid.UUID
    notes: str | None = Field(default=None, max_length=1000)
    items: list[PlanItemRequest] = Field(default_factory=list, max_length=100)


class PlanItemResponse(BaseModel):
    id: uuid.UUID
    procedure_code: str
    procedure_display: str
    tooth: int | None
    surface: str | None
    sequence: int
    status: str
    notes: str | None


class PlanResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    patient_id: uuid.UUID
    encounter_id: uuid.UUID | None
    practitioner_id: uuid.UUID
    status: str
    version: int
    notes: str | None
    items: list[PlanItemResponse]
    created_at: datetime
    updated_at: datetime


class PlanItemStatusRequest(BaseModel):
    status: str = Field(pattern=r"^(proposed|planned|in_progress|completed|cancelled)$")


class ProcedureRecordCreateRequest(BaseModel):
    procedure_code: str = Field(max_length=40)
    plan_item_id: uuid.UUID | None = None
    tooth: int | None = None
    surface: str | None = Field(default=None, max_length=16)
    notes: str | None = Field(default=None, max_length=1000)


class ProcedureRecordStatusRequest(BaseModel):
    status: str = Field(pattern=r"^(planned|in_progress|completed|cancelled)$")


class ProcedureRecordResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    encounter_id: uuid.UUID
    practitioner_id: uuid.UUID
    procedure_code: str
    procedure_display: str
    plan_item_id: uuid.UUID | None
    tooth: int | None
    surface: str | None
    status: str
    notes: str | None
    performed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ConsentCreateRequest(BaseModel):
    plan_id: uuid.UUID | None = None
    procedure_record_id: uuid.UUID | None = None
    consenter_name: str = Field(min_length=2, max_length=200)
    consenter_relation: str | None = Field(default=None, max_length=64)
    document_ref: str | None = Field(default=None, max_length=500)


class ConsentDecideRequest(BaseModel):
    decision: str = Field(pattern=r"^(granted|declined)$")


class ConsentResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    plan_id: uuid.UUID | None
    procedure_record_id: uuid.UUID | None
    status: str
    consenter_name: str
    consenter_relation: str | None
    document_ref: str | None
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RecallCreateRequest(BaseModel):
    patient_id: uuid.UUID
    practitioner_id: uuid.UUID | None = None
    location_id: uuid.UUID
    due_date: date
    reason: str = Field(min_length=2, max_length=200)


class RecallStatusRequest(BaseModel):
    status: str = Field(pattern=r"^(scheduled|completed|cancelled|missed)$")


class RecallResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    patient_id: uuid.UUID
    practitioner_id: uuid.UUID | None
    location_id: uuid.UUID
    due_date: date
    reason: str
    status: str
    created_at: datetime
    updated_at: datetime


class DocumentRefCreateRequest(BaseModel):
    doc_type: str = Field(default="other", max_length=32)
    storage_key: str = Field(min_length=1, max_length=500)
    content_type: str | None = Field(default=None, max_length=127)
    size_bytes: int | None = Field(default=None, ge=0)
    sha256: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=500)


class DocumentRefResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    encounter_id: uuid.UUID
    doc_type: str
    storage_key: str
    content_type: str | None
    size_bytes: int | None
    sha256: str | None
    notes: str | None
    created_at: datetime
