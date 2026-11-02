"""Tenancy + clinics schemas."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class TenantCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(min_length=2, max_length=120, pattern=r"^[a-z0-9][a-z0-9-]*$")


class TenantResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    status: str


class LocationCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    timezone: str = Field(default="Asia/Kolkata", max_length=64)


class LocationResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    timezone: str
    is_active: bool


class RoleCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    permissions: list[str]


class RoleResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID | None
    name: str
    permissions: list[str]
    is_seed: bool


class MembershipResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: str
    is_active: bool
    is_primary: bool
    location_ids: list[uuid.UUID]


class MembershipUpdateRequest(BaseModel):
    role: str | None = None
    is_active: bool | None = None
    location_ids: list[uuid.UUID] | None = None


class PractitionerCreateRequest(BaseModel):
    display_name: str = Field(min_length=2, max_length=200)
    user_id: uuid.UUID | None = None


class PractitionerResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    display_name: str
    is_active: bool


class VerificationRequest(BaseModel):
    practitioner_id: uuid.UUID
    status: str = Field(pattern=r"^(pending|approved|rejected)$")
    reason: str | None = None
