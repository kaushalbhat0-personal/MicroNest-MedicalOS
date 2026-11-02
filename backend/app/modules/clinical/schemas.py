"""Clinical schemas. Shape validation only; lifecycle and closure rules live
in the service. Note content fields are never echoed into audit or logs."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class EncounterOpenRequest(BaseModel):
    patient_id: uuid.UUID
    practitioner_id: uuid.UUID
    location_id: uuid.UUID
    appointment_id: uuid.UUID | None = None
    chief_complaint: str | None = Field(default=None, max_length=500)


class EncounterCloseRequest(BaseModel):
    note_waiver: bool = False
    vitals_waiver: bool = False
    reason: str | None = Field(default=None, max_length=200)


class EncounterResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    patient_id: uuid.UUID
    practitioner_id: uuid.UUID
    location_id: uuid.UUID
    appointment_id: uuid.UUID | None
    chief_complaint: str | None
    status: str
    version: int
    opened_by: uuid.UUID | None
    opened_at: datetime
    closed_by: uuid.UUID | None
    closed_at: datetime | None
    close_reason: str | None
    created_at: datetime
    updated_at: datetime


class EncounterListResponse(BaseModel):
    items: list[EncounterResponse]
    next_cursor: uuid.UUID | None


class NoteCreateRequest(BaseModel):
    note_type: str = Field(default="general", max_length=40)
    chief_complaint: str | None = Field(default=None, max_length=500)
    subjective: str | None = None
    objective: str | None = None
    assessment: str | None = None
    plan: str | None = None


class NoteResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    encounter_id: uuid.UUID
    author_id: uuid.UUID
    note_type: str
    chief_complaint: str | None
    subjective: str | None
    objective: str | None
    assessment: str | None
    plan: str | None
    status: str
    version: int
    is_addendum: bool
    supersedes_id: uuid.UUID | None
    superseded_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ObservationCreateRequest(BaseModel):
    type_code: str = Field(max_length=40)
    value_numeric: float
    value_text: str | None = Field(default=None, max_length=200)
    taken_at: datetime | None = None


class ObservationResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    encounter_id: uuid.UUID
    type_code: str
    type_display: str
    value_numeric: float
    value_text: str | None
    unit: str
    taken_at: datetime
    corrects_id: uuid.UUID | None
    corrected_by_id: uuid.UUID | None
    created_at: datetime


class ObservationTypeResponse(BaseModel):
    id: uuid.UUID
    code: str
    display: str
    unit: str
    min_value: float | None
    max_value: float | None
    is_active: bool


class DiagnosisCreateRequest(BaseModel):
    diagnosis_code: str | None = Field(default=None, max_length=40)
    free_text: str | None = Field(default=None, max_length=300)
    is_primary: bool = False
    onset_date: date | None = None


class DiagnosisResolveRequest(BaseModel):
    outcome: str = Field(pattern=r"^(resolved|ruled_out)$")


class DiagnosisResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    encounter_id: uuid.UUID
    diagnosis_code: str | None
    diagnosis_display: str | None
    free_text: str | None
    is_primary: bool
    status: str
    review_needed: bool
    onset_date: date | None
    supersedes_id: uuid.UUID | None
    superseded_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class DiagnosisCodeResponse(BaseModel):
    id: uuid.UUID
    code: str
    display: str
    icd10: str | None
    snomed: str | None
    needs_review: bool
    is_active: bool
