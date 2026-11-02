"""Identity schemas. Responses never contain hashes, secrets, or tokens
(tokens travel in HttpOnly cookies only)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.platform.security.passwords import MIN_PASSWORD_LENGTH


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TenantOption(BaseModel):
    id: uuid.UUID
    slug: str
    name: str


class MeResponse(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    is_platform_admin: bool
    tenants: list[TenantOption]


class SessionInfo(BaseModel):
    id: uuid.UUID
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime
    ip: str | None
    current: bool


class InviteCreateRequest(BaseModel):
    email: EmailStr
    role: str = Field(description="Seed role name or tenant custom role name")


class InviteCreateResponse(BaseModel):
    id: uuid.UUID
    email: str
    # Returned ONCE for delivery by the inviter's channel. Never stored.
    token: str
    expires_at: datetime


class InviteAcceptRequest(BaseModel):
    token: str
    display_name: str
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH)
