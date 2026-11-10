"""Tenancy + clinics schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TenantCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(min_length=2, max_length=120, pattern=r"^[a-z0-9][a-z0-9-]*$")


class TenantResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    status: str


class PlanLimits(BaseModel):
    """Configured plan caps. Informational and UNENFORCED in O1."""

    max_locations: int
    max_practitioners: int
    max_staff_seats: int
    enforced: bool = False


class SubscriptionSummary(BaseModel):
    """Minimum useful subscription information for a workspace.

    All values are server-resolved snapshots. `limits` are the plan's
    configured caps, presented as INFORMATIONAL ONLY — nothing in O1
    enforces them and reads never change clinical availability.
    `is_in_trial` is derived from persisted status + dates (no writes).
    """

    status: str
    trial_ends_at: datetime | None = None
    plan_code: str
    plan_name: str = ""
    trial_starts_at: datetime | None = None
    is_in_trial: bool = False
    limits: PlanLimits | None = None


class SpecialtyDetail(BaseModel):
    """One persisted specialty enablement row + registry readiness.

    `maturity` is "ready" | "discovery" | "unknown"; `ready_for_use` is a
    display predicate only and never gates authorization, RLS, identity,
    or subscription behavior.
    """

    code: str
    pack_version: str
    label: str
    maturity: str
    ready_for_use: bool


class TenantDetailResponse(BaseModel):
    """Tenant detail for the onboarding journey: base tenant + current
    subscription (None for pre-trial legacy tenants) + enabled specialties."""

    id: uuid.UUID
    name: str
    slug: str
    status: str
    subscription: SubscriptionSummary | None = None
    specialties_enabled: list[str] = []
    specialties: list[SpecialtyDetail] = []


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


class PractitionerStatus(BaseModel):
    id: uuid.UUID
    display_name: str
    verification_status: str


class VerificationRequest(BaseModel):
    practitioner_id: uuid.UUID
    status: str = Field(pattern=r"^(pending|approved|rejected)$")
    reason: str | None = None
