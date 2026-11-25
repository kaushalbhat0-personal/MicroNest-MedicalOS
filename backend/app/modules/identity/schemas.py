"""Identity schemas.

Browser login/refresh responses never contain tokens (HttpOnly cookies only).
Native JSON auth responses intentionally include access/refresh tokens for
desktop clients — see B0 native auth design.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.platform.security.passwords import MIN_PASSWORD_LENGTH


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class NativeLoginRequest(BaseModel):
    email: EmailStr
    password: str
    client_platform: Literal["windows", "android"] = "windows"
    device_label: str | None = Field(default=None, max_length=120)
    client_instance_id: str | None = Field(
        default=None,
        max_length=64,
        description="Opaque client install id (UUID string). Not proof-of-possession.",
    )


class NativeRefreshRequest(BaseModel):
    refresh_token: str = Field(
        min_length=10,
        description="Opaque refresh: {session_id}.{secret}",
    )


class TenantOption(BaseModel):
    id: uuid.UUID
    slug: str
    name: str


class NativeTokenResponse(BaseModel):
    """Native session bootstrap. Tokens must not be logged by clients."""

    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    id: uuid.UUID
    email: str
    display_name: str
    is_platform_admin: bool
    email_verified: bool
    tenants: list[TenantOption]
    session_id: uuid.UUID
    client_platform: str


class MeResponse(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    is_platform_admin: bool
    # Minimum verification exposure for O1.1: the shell decides between
    # "check your inbox" and normal routing. No challenge state leaks.
    email_verified: bool
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
    location_ids: list[uuid.UUID] | None = None
    ttl_days: int = Field(default=7, ge=1, le=30)


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


class InviteAcceptAuthenticatedRequest(BaseModel):
    token: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH)


class SignupRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)


class VerifyRequest(BaseModel):
    token: str = Field(min_length=1)


class VerifyResendRequest(BaseModel):
    email: EmailStr
