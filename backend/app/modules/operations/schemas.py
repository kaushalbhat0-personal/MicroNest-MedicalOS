"""Operations dashboard response schemas.

Metric definitions (source of truth):
- Appointment buckets match reception-queue `_bucket_queue`:
  waiting=scheduled|confirmed, checked_in, completed, no_show, cancelled.
- scheduled_today = count of appointments with start_at in the location
  service-day window (all statuses). Same window as reception_queue.
- in_consultation = open encounters at the location (not an appointment
  status; may overlap checked_in patients).
- follow_ups due_today/overdue/upcoming use location service-day COUNTs
  (communications.count_follow_ups_for_interval). Workspace UTC buckets
  unchanged.
- outstanding: complete SQL aggregate of issued|partially_paid invoices
  (draft/voided/paid excluded).
- payments_today: complete SUM/COUNT of payments with received_at in the
  location service day (refunded excluded).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time

from pydantic import BaseModel, Field


class AppointmentMetrics(BaseModel):
    scheduled_today: int
    waiting: int
    checked_in: int
    in_consultation: int
    completed: int
    cancelled: int
    no_show: int


class FollowUpMetrics(BaseModel):
    due_today: int
    overdue: int
    upcoming: int


class BillingMetrics(BaseModel):
    outstanding_invoice_count: int
    outstanding_amount: str
    currency: str = "INR"
    payments_today_count: int
    payments_today_amount: str


class AppointmentRow(BaseModel):
    id: uuid.UUID
    start_at: datetime
    end_at: datetime
    status: str
    patient_id: uuid.UUID
    patient_display_name: str
    practitioner_id: uuid.UUID
    practitioner_display_name: str
    location_id: uuid.UUID
    queue_token: int | None = None
    notes: str | None = None


class PractitionerWindow(BaseModel):
    practitioner_id: uuid.UUID
    display_name: str
    verification_status: str
    # Optional staff-schedule windows for the weekday (employment schedule).
    staff_windows: list[str] = Field(default_factory=list)


class ClinicHoursWindow(BaseModel):
    start_local: time
    end_local: time


class AvailabilitySummary(BaseModel):
    clinic_hours: list[ClinicHoursWindow]
    practitioners: list[PractitionerWindow]


class AppointmentListMeta(BaseModel):
    """Detail list is intentionally bounded; metrics remain complete COUNTs."""

    total: int
    returned: int
    truncated: bool
    limit: int


class OperationsDashboardResponse(BaseModel):
    tenant_id: uuid.UUID
    location_id: uuid.UUID
    location_name: str
    service_date: date
    timezone: str
    appointments: AppointmentMetrics | None = None
    reception: AppointmentMetrics | None = None
    follow_ups: FollowUpMetrics | None = None
    billing: BillingMetrics | None = None
    availability: AvailabilitySummary | None = None
    todays_appointments: list[AppointmentRow] = Field(default_factory=list)
    appointments_list: AppointmentListMeta | None = None
    sections_omitted: list[str] = Field(default_factory=list)
    follow_up_day_basis: str | None = Field(
        default=None,
        description="location_service_day for ops KPIs; workspace lists remain UTC.",
    )
