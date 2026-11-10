"""Portal link model: exactly one patient context per (user, tenant)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db import Base

LINK_ACTIVE = "active"
LINK_REVOKED = "revoked"


class PortalLink(Base):
    """Binds a portal user to one patient within one tenant.

    Ownership authority: portal endpoints resolve `patient_id` only from
    this row. The browser never supplies patient identity.
    """

    __tablename__ = "portal_links"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_portal_link_tenant_user"),
        CheckConstraint("status IN ('active','revoked')", name="ck_portal_link_status"),
        Index("ix_portal_links_tenant", "tenant_id"),
        Index("ix_portal_links_patient", "patient_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="RESTRICT", name="fk_portal_patient"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=LINK_ACTIVE)
    created_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True)
