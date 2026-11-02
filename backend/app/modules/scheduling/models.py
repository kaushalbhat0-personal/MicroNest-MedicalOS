"""Scheduling models. Tenant-owned. Status is a native Postgres enum
(stable P2+ state machine); instants are timestamptz, always UTC."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import TIMESTAMP, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db import Base

STATUS_SCHEDULED = "scheduled"
STATUS_CONFIRMED = "confirmed"
STATUS_CHECKED_IN = "checked_in"
STATUS_COMPLETED = "completed"
STATUS_CANCELLED = "cancelled"
STATUS_NO_SHOW = "no_show"

STATUSES = (
    STATUS_SCHEDULED,
    STATUS_CONFIRMED,
    STATUS_CHECKED_IN,
    STATUS_COMPLETED,
    STATUS_CANCELLED,
    STATUS_NO_SHOW,
)

AppointmentStatusEnum = sa.Enum(
    *STATUSES, name="appointment_status", native_enum=True, validate_strings=True
)


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False
    )
    practitioner_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("practitioners.id", ondelete="RESTRICT"),
        nullable=False,
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False
    )
    # UTC instants. `timezone` records the IANA zone the wall-clock input was
    # interpreted in (location default) — display context, never storage.
    start_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Kolkata")
    status: Mapped[str] = mapped_column(
        AppointmentStatusEnum, nullable=False, default=STATUS_SCHEDULED
    )
    # Operational note only (e.g. "bring prior reports"). Never clinical
    # content, never copied to audit/outbox payloads.
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    cancelled_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_appointments_tenant", "tenant_id"),
        Index("ix_appointments_patient", "patient_id"),
        Index("ix_appointments_practitioner", "practitioner_id"),
        Index("ix_appointments_location", "location_id"),
        Index("ix_appointments_tenant_start", "tenant_id", "start_at", "id"),
        Index(
            "uq_appointments_tenant_idem",
            "tenant_id",
            "idempotency_key",
            unique=True,
            postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        ),
    )
