"""Staff API schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time

from pydantic import BaseModel, Field


class StaffMemberResponse(BaseModel):
    membership_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    display_name: str
    role: str
    permissions: list[str]
    is_active: bool
    is_primary: bool
    location_ids: list[uuid.UUID]
    designation: str | None = None
    phone: str | None = None
    employment_status: str = "active"
    joined_at: date | None = None
    notes: str | None = None


class StaffProfileUpdateRequest(BaseModel):
    designation: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    employment_status: str | None = Field(
        default=None, pattern=r"^(active|on_leave|terminated)$"
    )
    joined_at: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
    location_ids: list[uuid.UUID] | None = None
    role: str | None = None
    is_active: bool | None = None


class InvitationListItem(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    status: str
    location_ids: list[uuid.UUID]
    expires_at: datetime
    created_at: datetime
    invited_by: uuid.UUID | None


class InviteCreateBody(BaseModel):
    email: str
    role: str
    location_ids: list[uuid.UUID] | None = None
    ttl_days: int = Field(default=7, ge=1, le=30)


class ScheduleCreateRequest(BaseModel):
    membership_id: uuid.UUID
    location_id: uuid.UUID
    weekday: int = Field(ge=0, le=6)
    start_time: time
    end_time: time
    break_minutes: int = Field(default=0, ge=0, le=480)
    effective_from: date
    effective_to: date | None = None


class ScheduleResponse(BaseModel):
    id: uuid.UUID
    membership_id: uuid.UUID
    location_id: uuid.UUID
    weekday: int
    start_time: time
    end_time: time
    break_minutes: int
    effective_from: date
    effective_to: date | None
    is_active: bool


class CheckInRequest(BaseModel):
    location_id: uuid.UUID


class CheckOutRequest(BaseModel):
    attendance_id: uuid.UUID | None = None


class AttendanceCorrectRequest(BaseModel):
    check_in_at: datetime | None = None
    check_out_at: datetime | None = None
    reason: str = Field(min_length=3, max_length=300)


class AttendanceResponse(BaseModel):
    id: uuid.UUID
    membership_id: uuid.UUID
    location_id: uuid.UUID
    attendance_date: date
    check_in_at: datetime
    check_out_at: datetime | None
    source: str
    correction_reason: str | None
    duration_minutes: int | None


class LeaveTypeCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)


class LeaveTypeResponse(BaseModel):
    id: uuid.UUID
    name: str
    is_active: bool


class LeaveCreateRequest(BaseModel):
    leave_type_id: uuid.UUID
    start_date: date
    end_date: date
    reason: str | None = Field(default=None, max_length=500)


class LeaveDecideRequest(BaseModel):
    decision: str = Field(pattern=r"^(approved|rejected)$")
    note: str | None = Field(default=None, max_length=300)


class LeaveResponse(BaseModel):
    id: uuid.UUID
    membership_id: uuid.UUID
    leave_type_id: uuid.UUID
    leave_type_name: str
    start_date: date
    end_date: date
    reason: str | None
    status: str
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    decision_note: str | None
    created_at: datetime
