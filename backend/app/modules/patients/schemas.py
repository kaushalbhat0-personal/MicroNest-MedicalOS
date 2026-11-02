"""Patient schemas. Identity only — no clinical fields exist at this layer."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class PatientCreateRequest(BaseModel):
    display_name: str = Field(min_length=2, max_length=200)
    phone: str | None = Field(default=None, max_length=32)


class PatientResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    display_name: str
    phone: str | None
    is_active: bool
