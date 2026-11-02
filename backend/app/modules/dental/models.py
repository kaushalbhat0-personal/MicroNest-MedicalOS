"""Dental models. FDI tooth identity is validated in the service (centralized
domain rule). Findings reference encounters; plans reference patients with
an optional encounter link. Money fields do not exist at this layer."""

from __future__ import annotations

import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db import Base

FINDING_ACTIVE = "active"
FINDING_RESOLVED = "resolved"
FINDING_STATUSES = (FINDING_ACTIVE, FINDING_RESOLVED)

PLAN_DRAFT = "draft"
PLAN_ACTIVE = "active"
PLAN_COMPLETED = "completed"
PLAN_CANCELLED = "cancelled"
PLAN_STATUSES = (PLAN_DRAFT, PLAN_ACTIVE, PLAN_COMPLETED, PLAN_CANCELLED)

ITEM_PROPOSED = "proposed"
ITEM_PLANNED = "planned"
ITEM_IN_PROGRESS = "in_progress"
ITEM_COMPLETED = "completed"
ITEM_CANCELLED = "cancelled"
ITEM_STATUSES = (ITEM_PROPOSED, ITEM_PLANNED, ITEM_IN_PROGRESS, ITEM_COMPLETED, ITEM_CANCELLED)

RECORD_PLANNED = "planned"
RECORD_IN_PROGRESS = "in_progress"
RECORD_COMPLETED = "completed"
RECORD_CANCELLED = "cancelled"
RECORD_STATUSES = (RECORD_PLANNED, RECORD_IN_PROGRESS, RECORD_COMPLETED, RECORD_CANCELLED)

CONSENT_PENDING = "pending"
CONSENT_GRANTED = "granted"
CONSENT_DECLINED = "declined"
CONSENT_WITHDRAWN = "withdrawn"
CONSENT_STATUSES = (CONSENT_PENDING, CONSENT_GRANTED, CONSENT_DECLINED, CONSENT_WITHDRAWN)

RECALL_SCHEDULED = "scheduled"
RECALL_COMPLETED = "completed"
RECALL_CANCELLED = "cancelled"
RECALL_MISSED = "missed"
RECALL_STATUSES = (RECALL_SCHEDULED, RECALL_COMPLETED, RECALL_CANCELLED, RECALL_MISSED)


class DentalCondition(Base):
    """Global dental condition catalog. Reference data: read-only."""

    __tablename__ = "dental_conditions"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    display: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ToothFinding(Base):
    """A condition observed on a tooth in an encounter context. Facts
    accumulate over time; resolution/supersede never rewrites history."""

    __tablename__ = "tooth_findings"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    encounter_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("encounters.id", ondelete="RESTRICT"), nullable=False
    )
    practitioner_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("practitioners.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tooth: Mapped[int] = mapped_column(Integer, nullable=False)
    condition_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("dental_conditions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        sa.Enum(*FINDING_STATUSES, name="finding_status", native_enum=True, validate_strings=True),
        nullable=False,
        default=FINDING_ACTIVE,
    )
    details: Mapped[str | None] = mapped_column(String(500), nullable=True)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_findings_tenant", "tenant_id"),
        Index("ix_findings_encounter", "encounter_id"),
        Index("ix_findings_tooth", "tenant_id", "tooth"),
    )


class ToothFindingSurface(Base):
    """Normalized tooth surfaces for a finding. Domain-controlled set only
    (validated against the FDI surface list in the service)."""

    __tablename__ = "tooth_finding_surfaces"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    finding_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tooth_findings.id", ondelete="CASCADE"),
        nullable=False,
    )
    surface: Mapped[str] = mapped_column(String(16), nullable=False)

    __table_args__ = (
        Index("ix_finding_surfaces_finding", "finding_id"),
        sa.UniqueConstraint("finding_id", "surface", name="uq_finding_surface"),
    )


class DentalProcedure(Base):
    """Global clinical procedure catalog (what exists). Records of performed
    procedures live in dental_procedure_records (what was done)."""

    __tablename__ = "dental_procedures"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    display: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    specialty: Mapped[str] = mapped_column(String(40), nullable=False, default="general")
    external_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class TreatmentPlan(Base):
    """Clinical plan for a patient. Not an estimate, not an invoice — money
    lives in P4. Status transitions are service-owned."""

    __tablename__ = "treatment_plans"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False
    )
    encounter_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("encounters.id", ondelete="RESTRICT"), nullable=True
    )
    practitioner_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("practitioners.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        sa.Enum(*PLAN_STATUSES, name="plan_status", native_enum=True, validate_strings=True),
        nullable=False,
        default=PLAN_DRAFT,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_plans_tenant", "tenant_id"),
        Index("ix_plans_patient", "patient_id"),
    )


class TreatmentPlanItem(Base):
    __tablename__ = "treatment_plan_items"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("treatment_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    procedure_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("dental_procedures.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tooth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    surface: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        sa.Enum(*ITEM_STATUSES, name="plan_item_status", native_enum=True, validate_strings=True),
        nullable=False,
        default=ITEM_PROPOSED,
    )
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (Index("ix_plan_items_plan", "plan_id"),)


class DentalProcedureRecord(Base):
    """What was planned/performed for this patient (vs the catalog). Content
    immutable; lifecycle transitions only."""

    __tablename__ = "dental_procedure_records"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    encounter_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("encounters.id", ondelete="RESTRICT"), nullable=False
    )
    practitioner_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("practitioners.id", ondelete="RESTRICT"),
        nullable=False,
    )
    procedure_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("dental_procedures.id", ondelete="RESTRICT"),
        nullable=False,
    )
    plan_item_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("treatment_plan_items.id", ondelete="RESTRICT"),
        nullable=True,
    )
    tooth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    surface: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(
        sa.Enum(
            *RECORD_STATUSES,
            name="procedure_record_status",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
        default=RECORD_PLANNED,
    )
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    performed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_procrec_tenant", "tenant_id"),
        Index("ix_procrec_encounter", "encounter_id"),
    )


class Consent(Base):
    """Minimum structured consent relationship for plans/procedures. Exactly
    one subject. Signed documents live in storage; only the reference is kept."""

    __tablename__ = "consents"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("treatment_plans.id", ondelete="RESTRICT"),
        nullable=True,
    )
    procedure_record_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("dental_procedure_records.id", ondelete="RESTRICT"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        sa.Enum(*CONSENT_STATUSES, name="consent_status", native_enum=True, validate_strings=True),
        nullable=False,
        default=CONSENT_PENDING,
    )
    consenter_name: Mapped[str] = mapped_column(String(200), nullable=False)
    consenter_relation: Mapped[str | None] = mapped_column(String(64), nullable=True)
    document_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_consents_tenant", "tenant_id"),
        CheckConstraint(
            "(plan_id IS NULL) <> (procedure_record_id IS NULL)",
            name="ck_consent_single_subject",
        ),
    )


class Recall(Base):
    """Clinical/operational recall (review date). Not a campaign engine —
    no audiences, no templates, no automation in P3."""

    __tablename__ = "recalls"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False
    )
    practitioner_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("practitioners.id", ondelete="RESTRICT"),
        nullable=True,
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False
    )
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.Enum(*RECALL_STATUSES, name="recall_status", native_enum=True, validate_strings=True),
        nullable=False,
        default=RECALL_SCHEDULED,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_recalls_tenant", "tenant_id"),
        Index("ix_recalls_patient", "patient_id"),
        Index("ix_recalls_due", "tenant_id", "due_date"),
    )


class DocumentReference(Base):
    """Metadata pointer to a stored object (X-ray, scan, photo, report).
    Bytes live behind the storage port; the DB keeps references only, and
    references are never public URLs (signed access via the port)."""

    __tablename__ = "document_references"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    encounter_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("encounters.id", ondelete="RESTRICT"), nullable=False
    )
    doc_type: Mapped[str] = mapped_column(String(32), nullable=False, default="other")
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(127), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_docrefs_tenant", "tenant_id"),
        Index("ix_docrefs_encounter", "encounter_id"),
    )
