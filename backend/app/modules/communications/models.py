"""Follow-up, communication-consent, and communication-log tables.

Dental clinical consent (`consents`) remains separate. This module stores
purpose+channel communication preferences and staff interaction logs only.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import TIMESTAMP, Boolean, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db import Base

# --- Follow-ups ---

FU_OPEN = "open"
FU_IN_PROGRESS = "in_progress"
FU_SNOOZED = "snoozed"
FU_COMPLETED = "completed"
FU_CANCELLED = "cancelled"
FOLLOWUP_STATUSES = (FU_OPEN, FU_IN_PROGRESS, FU_SNOOZED, FU_COMPLETED, FU_CANCELLED)
FOLLOWUP_ACTIVE = frozenset({FU_OPEN, FU_IN_PROGRESS, FU_SNOOZED})

FU_PRI_LOW = "low"
FU_PRI_NORMAL = "normal"
FU_PRI_HIGH = "high"
FU_PRI_URGENT = "urgent"
FOLLOWUP_PRIORITIES = (FU_PRI_LOW, FU_PRI_NORMAL, FU_PRI_HIGH, FU_PRI_URGENT)

FU_CAT_ENCOUNTER = "encounter"
FU_CAT_TREATMENT_PLAN = "treatment_plan"
FU_CAT_PRESCRIPTION = "prescription"
FU_CAT_APPOINTMENT = "appointment"
FU_CAT_MANUAL = "manual"
FU_CAT_OTHER = "other"
FOLLOWUP_CATEGORIES = (
    FU_CAT_ENCOUNTER,
    FU_CAT_TREATMENT_PLAN,
    FU_CAT_PRESCRIPTION,
    FU_CAT_APPOINTMENT,
    FU_CAT_MANUAL,
    FU_CAT_OTHER,
)

FU_SRC_ENCOUNTER = "encounter"
FU_SRC_TREATMENT_PLAN = "treatment_plan"
FU_SRC_PRESCRIPTION = "prescription"
FU_SRC_APPOINTMENT = "appointment"
FU_SRC_MANUAL = "manual"
FOLLOWUP_SOURCE_TYPES = (
    FU_SRC_ENCOUNTER,
    FU_SRC_TREATMENT_PLAN,
    FU_SRC_PRESCRIPTION,
    FU_SRC_APPOINTMENT,
    FU_SRC_MANUAL,
)

# --- Communication consent (channel × purpose) ---

CH_PHONE = "phone"
CH_EMAIL = "email"
CH_WHATSAPP = "whatsapp"
CH_SMS = "sms"
CH_IN_PERSON = "in_person"
CH_OTHER = "other"
COMM_CHANNELS = (CH_PHONE, CH_EMAIL, CH_WHATSAPP, CH_SMS, CH_IN_PERSON, CH_OTHER)
CONSENT_CHANNELS = (CH_PHONE, CH_EMAIL, CH_WHATSAPP, CH_SMS)

PURPOSE_APPOINTMENT_REMINDER = "appointment_reminder"
PURPOSE_CARE_FOLLOWUP = "care_followup"
PURPOSE_ADMINISTRATIVE = "administrative"
PURPOSE_MARKETING = "marketing"
COMM_PURPOSES = (
    PURPOSE_APPOINTMENT_REMINDER,
    PURPOSE_CARE_FOLLOWUP,
    PURPOSE_ADMINISTRATIVE,
    PURPOSE_MARKETING,
)

CC_GRANTED = "granted"
CC_DENIED = "denied"
CC_REVOKED = "revoked"
COMM_CONSENT_STATUSES = (CC_GRANTED, CC_DENIED, CC_REVOKED)
# "unknown" is the absence of a current row — never stored.

CAPTURE_STAFF = "staff"
CAPTURE_PORTAL = "portal"
CAPTURE_IMPORT = "import"
CAPTURE_OTHER = "other"
CAPTURE_SOURCES = (CAPTURE_STAFF, CAPTURE_PORTAL, CAPTURE_IMPORT, CAPTURE_OTHER)

# --- Communication log ---

OUT_CONTACTED = "contacted"
OUT_NO_ANSWER = "no_answer"
OUT_CALLBACK = "callback_requested"
OUT_DECLINED = "declined"
OUT_BAD_CONTACT = "incorrect_contact"
OUT_FOLLOWUP_SCHEDULED = "follow_up_scheduled"
COMM_OUTCOMES = (
    OUT_CONTACTED,
    OUT_NO_ANSWER,
    OUT_CALLBACK,
    OUT_DECLINED,
    OUT_BAD_CONTACT,
    OUT_FOLLOWUP_SCHEDULED,
)


class FollowUp(Base):
    """Operational follow-up task. References source records by type+id;
    does not copy clinical payloads."""

    __tablename__ = "follow_ups"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False
    )
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    due_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    category: Mapped[str] = mapped_column(
        sa.Enum(
            *FOLLOWUP_CATEGORIES,
            name="followup_category",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    source_type: Mapped[str] = mapped_column(
        sa.Enum(
            *FOLLOWUP_SOURCE_TYPES,
            name="followup_source_type",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
        default=FU_SRC_MANUAL,
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    priority: Mapped[str] = mapped_column(
        sa.Enum(
            *FOLLOWUP_PRIORITIES,
            name="followup_priority",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
        default=FU_PRI_NORMAL,
    )
    status: Mapped[str] = mapped_column(
        sa.Enum(
            *FOLLOWUP_STATUSES,
            name="followup_status",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
        default=FU_OPEN,
    )
    outcome: Mapped[str | None] = mapped_column(String(64), nullable=True)
    next_action: Mapped[str | None] = mapped_column(String(200), nullable=True)
    next_due_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    snooze_until: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    completed_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_followups_tenant", "tenant_id"),
        Index("ix_followups_patient", "patient_id"),
        Index("ix_followups_due", "tenant_id", "due_at"),
        Index("ix_followups_assignee", "tenant_id", "assigned_user_id"),
        Index("ix_followups_status", "tenant_id", "status"),
        Index(
            "uq_followups_active_source",
            "tenant_id",
            "source_type",
            "source_id",
            "category",
            unique=True,
            postgresql_where=sa.text(
                "status IN ('open', 'in_progress', 'snoozed') AND source_id IS NOT NULL"
            ),
        ),
    )


class CommunicationConsent(Base):
    """Current purpose×channel communication preference for a patient.

    Historical changes are recorded via audit events and by inserting a new
    row that supersedes the previous current row (never silent overwrite).
    """

    __tablename__ = "communication_consents"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False
    )
    channel: Mapped[str] = mapped_column(
        sa.Enum(
            *CONSENT_CHANNELS,
            name="comm_consent_channel",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
    )
    purpose: Mapped[str] = mapped_column(
        sa.Enum(
            *COMM_PURPOSES,
            name="comm_consent_purpose",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        sa.Enum(
            *COMM_CONSENT_STATUSES,
            name="comm_consent_status",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
    )
    capture_source: Mapped[str] = mapped_column(
        sa.Enum(
            *CAPTURE_SOURCES,
            name="comm_consent_capture",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
        default=CAPTURE_STAFF,
    )
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("communication_consents.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_comm_consent_tenant", "tenant_id"),
        Index("ix_comm_consent_patient", "patient_id"),
        Index(
            "uq_comm_consent_current",
            "tenant_id",
            "patient_id",
            "channel",
            "purpose",
            unique=True,
            postgresql_where=sa.text("is_current IS TRUE"),
        ),
    )


class CommunicationLog(Base):
    """Staff-confirmed interaction. Never stores message bodies."""

    __tablename__ = "communication_logs"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("locations.id", ondelete="SET NULL"), nullable=True
    )
    follow_up_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("follow_ups.id", ondelete="SET NULL"), nullable=True
    )
    channel: Mapped[str] = mapped_column(
        sa.Enum(
            *COMM_CHANNELS,
            name="comm_log_channel",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
    )
    purpose: Mapped[str] = mapped_column(
        sa.Enum(
            *COMM_PURPOSES,
            name="comm_log_purpose",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
    )
    outcome: Mapped[str] = mapped_column(
        sa.Enum(
            *COMM_OUTCOMES,
            name="comm_log_outcome",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
    )
    staff_user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(String(280), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_comm_logs_tenant", "tenant_id"),
        Index("ix_comm_logs_patient", "patient_id"),
        Index("ix_comm_logs_followup", "follow_up_id"),
        Index("ix_comm_logs_occurred", "tenant_id", "occurred_at"),
    )
