"""Workspace provisioning persistence: specialty enablement + idempotency.

`tenant_specialties` is the initial source of truth for enabled packs.
Locations inherit the tenant's enabled set by convention — there is no
`location_specialties` table in O1.2a (deferred until a real operational
requirement is demonstrated).

`workspace_provisions` is the durable per-user idempotency ledger. The key
is scoped to the authenticated user (UNIQUE(user_id, idempotency_key)) so
keys never leak existence across users.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CHAR, JSON, TIMESTAMP, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db import Base

PROVISION_PENDING = "pending"
PROVISION_COMPLETED = "completed"
PROVISION_FAILED = "failed"


class TenantSpecialty(Base):
    """Relational enablement set: one row per enabled pack per tenant."""

    __tablename__ = "tenant_specialties"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    specialty_code: Mapped[str] = mapped_column(Text, primary_key=True)
    pack_version: Mapped[str] = mapped_column(Text, nullable=False)
    enabled_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    enabled_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class WorkspaceProvision(Base):
    """Durable idempotency record for `POST /api/v1/workspaces`.

    Written in the SAME transaction as the provisioned rows: a rollback
    leaves zero rows here and everywhere else. `result_refs` carries ids
    only (never clinical data, secrets, or tokens) for replay responses.
    """

    __tablename__ = "workspace_provisions"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=PROVISION_PENDING)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )
    result_refs: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
