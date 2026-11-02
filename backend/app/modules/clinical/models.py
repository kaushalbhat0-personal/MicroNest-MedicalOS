"""Clinical models. Tenant-owned facts; global read-only catalogs.

Conventions: timestamptz UTC, UUIDv7 PKs, NUMERIC for decimals, native PG
enums for lifecycles, RESTRICT on clinical references (history is never
cascade-deleted), CASCADE only from the tenant root.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy import TIMESTAMP, Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db import Base

ENCOUNTER_OPEN = "open"
ENCOUNTER_CLOSED = "closed"
ENCOUNTER_STATUSES = (ENCOUNTER_OPEN, ENCOUNTER_CLOSED)

NOTE_DRAFT = "draft"
NOTE_FINALIZED = "finalized"
NOTE_AMENDED = "amended"
NOTE_STATUSES = (NOTE_DRAFT, NOTE_FINALIZED, NOTE_AMENDED)

DX_ACTIVE = "active"
DX_RESOLVED = "resolved"
DX_RULED_OUT = "ruled_out"
DX_SUPERSEDED = "superseded"
DX_STATUSES = (DX_ACTIVE, DX_RESOLVED, DX_RULED_OUT, DX_SUPERSEDED)


class Encounter(Base):
    __tablename__ = "encounters"

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
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("appointments.id", ondelete="RESTRICT"),
        nullable=True,
    )
    chief_complaint: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        sa.Enum(
            *ENCOUNTER_STATUSES, name="encounter_status", native_enum=True, validate_strings=True
        ),
        nullable=False,
        default=ENCOUNTER_OPEN,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    opened_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    closed_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    close_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_encounters_tenant", "tenant_id"),
        Index("ix_encounters_patient", "patient_id"),
        Index("ix_encounters_practitioner", "practitioner_id"),
        Index("ix_encounters_tenant_opened", "tenant_id", "opened_at", "id"),
    )


class ClinicalNote(Base):
    """General clinical note with optional SOAP-shaped fields. Finalized notes
    are immutable; corrections are new notes linked via supersedes_id."""

    __tablename__ = "clinical_notes"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    encounter_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("encounters.id", ondelete="RESTRICT"), nullable=False
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("practitioners.id", ondelete="RESTRICT"), nullable=False
    )
    note_type: Mapped[str] = mapped_column(String(40), nullable=False, default="general")
    chief_complaint: Mapped[str | None] = mapped_column(String(500), nullable=True)
    subjective: Mapped[str | None] = mapped_column(Text, nullable=True)
    objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    assessment: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        sa.Enum(*NOTE_STATUSES, name="note_status", native_enum=True, validate_strings=True),
        nullable=False,
        default=NOTE_DRAFT,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_addendum: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("clinical_notes.id", ondelete="RESTRICT"), nullable=True
    )
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("clinical_notes.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_notes_tenant", "tenant_id"),
        Index("ix_notes_encounter", "encounter_id"),
    )


class ObservationType(Base):
    """Global vitals/observation catalog. Reference data: no tenant, no RLS,
    read-only (no write endpoints; asserted by contract tests)."""

    __tablename__ = "observation_types"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    display: Mapped[str] = mapped_column(String(200), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    min_value: Mapped[float | None] = mapped_column(sa.Numeric(12, 3), nullable=True)
    max_value: Mapped[float | None] = mapped_column(sa.Numeric(12, 3), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Observation(Base):
    """Typed vital/observation fact. Immutable once recorded; corrections are
    new rows linked via corrects_id (old row marked corrected_by_id)."""

    __tablename__ = "observations"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    encounter_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("encounters.id", ondelete="RESTRICT"), nullable=False
    )
    type_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("observation_types.id", ondelete="RESTRICT"),
        nullable=False,
    )
    value_numeric: Mapped[float] = mapped_column(sa.Numeric(12, 3), nullable=False)
    value_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    taken_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    corrects_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("observations.id", ondelete="RESTRICT"), nullable=True
    )
    corrected_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("observations.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_observations_tenant", "tenant_id"),
        Index("ix_observations_encounter", "encounter_id"),
    )


class DiagnosisCode(Base):
    """Global diagnosis catalog with external-code mapping. Reference data:
    no tenant, no RLS, read-only."""

    __tablename__ = "diagnosis_codes"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    display: Mapped[str] = mapped_column(String(300), nullable=False)
    icd10: Mapped[str | None] = mapped_column(String(16), nullable=True)
    snomed: Mapped[str | None] = mapped_column(String(32), nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class EncounterDiagnosis(Base):
    """Diagnosis attached to an encounter. Exactly one of code/free-text.
    Corrections supersede; resolved/ruled-out are terminal for the row."""

    __tablename__ = "encounter_diagnoses"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    encounter_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("encounters.id", ondelete="RESTRICT"), nullable=False
    )
    diagnosis_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("diagnosis_codes.id", ondelete="RESTRICT"),
        nullable=True,
    )
    free_text: Mapped[str | None] = mapped_column(String(300), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(
        sa.Enum(*DX_STATUSES, name="diagnosis_status", native_enum=True, validate_strings=True),
        nullable=False,
        default=DX_ACTIVE,
    )
    review_needed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    onset_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("encounter_diagnoses.id", ondelete="RESTRICT"),
        nullable=True,
    )
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("encounter_diagnoses.id", ondelete="RESTRICT"),
        nullable=True,
    )
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_encdx_tenant", "tenant_id"),
        Index("ix_encdx_encounter", "encounter_id"),
        CheckConstraint(
            "(diagnosis_id IS NULL) <> (free_text IS NULL)",
            name="ck_encdx_coded_xor_free",
        ),
    )
