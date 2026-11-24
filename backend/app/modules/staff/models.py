"""Staff workforce models. Membership remains the employment attachment;
profiles/schedules/attendance/leave hang off membership + tenant."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time

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
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db import Base

EMP_ACTIVE = "active"
EMP_ON_LEAVE = "on_leave"
EMP_TERMINATED = "terminated"
EMP_STATUSES = (EMP_ACTIVE, EMP_ON_LEAVE, EMP_TERMINATED)

ATT_SOURCE_SELF = "self"
ATT_SOURCE_MANUAL = "manual"
ATT_SOURCES = (ATT_SOURCE_SELF, ATT_SOURCE_MANUAL)

LEAVE_PENDING = "pending"
LEAVE_APPROVED = "approved"
LEAVE_REJECTED = "rejected"
LEAVE_CANCELLED = "cancelled"
LEAVE_STATUSES = (LEAVE_PENDING, LEAVE_APPROVED, LEAVE_REJECTED, LEAVE_CANCELLED)


class StaffProfile(Base):
    """Employment metadata for a membership. Professional credentials stay
    on practitioners/verifications — this is workforce info only."""

    __tablename__ = "staff_profiles"

    membership_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("memberships.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    designation: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    employment_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=EMP_ACTIVE
    )
    joined_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_staff_profiles_tenant", "tenant_id"),
        CheckConstraint(
            "employment_status IN ('active', 'on_leave', 'terminated')",
            name="ck_staff_employment_status",
        ),
    )


class StaffSchedule(Base):
    """Staff working schedule (not clinic hours, not practitioner slots)."""

    __tablename__ = "staff_schedules"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    membership_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("memberships.id", ondelete="CASCADE"), nullable=False
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False
    )
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=Mon .. 6=Sun
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    break_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_staff_schedules_tenant", "tenant_id"),
        Index("ix_staff_schedules_member", "membership_id"),
        CheckConstraint("weekday >= 0 AND weekday <= 6", name="ck_staff_sched_weekday"),
        CheckConstraint("break_minutes >= 0", name="ck_staff_sched_break"),
        CheckConstraint("start_time < end_time", name="ck_staff_sched_times"),
    )


class AttendanceRecord(Base):
    """Basic attendance. Timestamps are server-authored. No GPS/biometrics."""

    __tablename__ = "attendance_records"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    membership_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("memberships.id", ondelete="CASCADE"), nullable=False
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False
    )
    attendance_date: Mapped[date] = mapped_column(Date, nullable=False)
    check_in_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    check_out_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default=ATT_SOURCE_SELF)
    corrected_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    correction_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_attendance_tenant_date", "tenant_id", "attendance_date"),
        Index("ix_attendance_member", "membership_id"),
        Index(
            "uq_attendance_open_checkin",
            "membership_id",
            unique=True,
            postgresql_where=sa.text("check_out_at IS NULL"),
        ),
        CheckConstraint(
            "source IN ('self', 'manual')",
            name="ck_attendance_source",
        ),
        CheckConstraint(
            "check_out_at IS NULL OR check_out_at > check_in_at",
            name="ck_attendance_checkout_after",
        ),
    )


class LeaveType(Base):
    __tablename__ = "leave_types"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_leave_types_tenant_name"),
        Index("ix_leave_types_tenant", "tenant_id"),
    )


class LeaveRequest(Base):
    __tablename__ = "leave_requests"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    membership_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("memberships.id", ondelete="CASCADE"), nullable=False
    )
    leave_type_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("leave_types.id", ondelete="RESTRICT"), nullable=False
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=LEAVE_PENDING)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_leave_requests_tenant", "tenant_id"),
        Index("ix_leave_requests_member", "membership_id"),
        CheckConstraint("end_date >= start_date", name="ck_leave_date_order"),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'cancelled')",
            name="ck_leave_status",
        ),
    )
