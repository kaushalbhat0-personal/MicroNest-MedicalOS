"""Workspace provisioning schemas (O1.2a).

The request carries NO owner/user ids: the owner is derived exclusively
from the authenticated server-side identity. Extra fields are ignored,
never trusted.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class WorkspaceCreateRequest(BaseModel):
    clinic_name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=120)
    location_name: str = Field(default="Main Clinic", min_length=1, max_length=200)
    timezone: str = Field(default="Asia/Kolkata", max_length=64)
    practitioner_display_name: str | None = Field(default=None, max_length=200)
    # Explicit selection, no silent default: empty means 422 (the dental
    # default is proposed, not approved — see the O1.2a delivery note).
    specialty_codes: list[str] = Field(min_length=1, max_length=10)


class TenantRef(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    status: str


class LocationRef(BaseModel):
    id: uuid.UUID
    name: str
    timezone: str


class MembershipRef(BaseModel):
    id: uuid.UUID
    role: str


class PractitionerRef(BaseModel):
    id: uuid.UUID
    display_name: str


class SubscriptionRef(BaseModel):
    id: uuid.UUID
    status: str
    trial_ends_at: datetime | None
    plan_code: str


class WorkspaceResponse(BaseModel):
    tenant: TenantRef
    location: LocationRef
    membership: MembershipRef
    practitioner: PractitionerRef
    specialties_enabled: list[str]
    subscription: SubscriptionRef
