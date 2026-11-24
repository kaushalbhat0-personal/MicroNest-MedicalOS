"""Portal response schemas: explicit patient-visible projections.

Every schema exposes only fields approved for patient display. Staff UUIDs,
internal actor refs, idempotency keys, storage keys, and provider metadata
are never serialized here — even when the underlying domain row has them.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PortalPatient(BaseModel):
    id: uuid.UUID
    display_name: str
    phone: str | None
    email: str | None = None
    is_active: bool


class PortalBookableLocation(BaseModel):
    id: uuid.UUID
    name: str
    timezone: str


class PortalBookablePractitioner(BaseModel):
    id: uuid.UUID
    display_name: str


class PortalAvailabilitySlot(BaseModel):
    start_at: datetime
    end_at: datetime


class PortalAvailability(BaseModel):
    practitioner_id: uuid.UUID
    location_id: uuid.UUID
    timezone: str
    date: str
    slot_minutes: int
    slots: list[PortalAvailabilitySlot]


class PortalAppointmentBook(BaseModel):
    practitioner_id: uuid.UUID
    location_id: uuid.UUID
    start: datetime
    duration_minutes: int = Field(default=30, ge=5, le=480)
    idempotency_key: str | None = Field(default=None, max_length=64)


class PortalMe(BaseModel):
    user_id: uuid.UUID
    email: str
    display_name: str
    tenant_id: uuid.UUID
    tenant_name: str
    patient: PortalPatient


class PortalAppointment(BaseModel):
    id: uuid.UUID
    start_at: datetime
    end_at: datetime
    timezone: str
    status: str
    location_id: uuid.UUID
    notes: str | None = None


class PortalAppointmentCancel(BaseModel):
    reason: str | None = Field(default=None, max_length=200)


class PortalEncounter(BaseModel):
    id: uuid.UUID
    status: str
    opened_at: datetime
    closed_at: datetime | None = None
    location_id: uuid.UUID


class PortalNote(BaseModel):
    id: uuid.UUID
    note_type: str
    status: str
    is_addendum: bool
    subjective: str | None = None
    objective: str | None = None
    assessment: str | None = None
    plan: str | None = None
    created_at: datetime


class PortalObservation(BaseModel):
    id: uuid.UUID
    type_code: str
    value: str
    unit: str | None = None
    recorded_at: datetime


class PortalDiagnosis(BaseModel):
    id: uuid.UUID
    status: str
    code: str | None = None
    display: str | None = None
    free_text: str | None = None


class PortalEncounterDetail(PortalEncounter):
    notes: list[PortalNote] = []
    observations: list[PortalObservation] = []
    diagnoses: list[PortalDiagnosis] = []


class PortalPrescriptionItem(BaseModel):
    medication_code: str
    dose: str
    route: str
    frequency: str
    duration_days: int | None = None
    quantity: str | None = None
    instructions: str | None = None


class PortalPrescription(BaseModel):
    id: uuid.UUID
    status: str
    version: int
    items: list[PortalPrescriptionItem] = []
    signed_at: datetime | None = None
    created_at: datetime


class PortalPlanItem(BaseModel):
    id: uuid.UUID
    procedure_code: str
    procedure_display: str | None = None
    tooth: int | None = None
    surface: str | None = None
    status: str
    notes: str | None = None


class PortalTreatmentPlan(BaseModel):
    id: uuid.UUID
    status: str
    version: int
    notes: str | None = None
    items: list[PortalPlanItem] = []


class PortalRecall(BaseModel):
    id: uuid.UUID
    due_date: str
    reason: str
    status: str
    location_id: uuid.UUID


class PortalConsent(BaseModel):
    id: uuid.UUID
    status: str
    consenter_name: str
    consenter_relation: str | None = None
    decided_at: datetime | None = None


class PortalDocument(BaseModel):
    id: uuid.UUID
    doc_type: str
    content_type: str | None = None
    size_bytes: int | None = None
    created_at: datetime
    download_available: bool = False


class PortalMoneyLine(BaseModel):
    description: str
    quantity: str
    unit_rate: str
    line_total: str


class PortalEstimate(BaseModel):
    id: uuid.UUID
    status: str
    currency: str
    subtotal: str
    tax_total: str
    grand_total: str
    valid_until: str | None = None
    lines: list[PortalMoneyLine] = []


class PortalInvoice(BaseModel):
    id: uuid.UUID
    status: str
    currency: str
    subtotal: str
    tax_total: str
    grand_total: str
    allocated_amount: str
    outstanding_amount: str
    due_date: str | None = None
    lines: list[PortalMoneyLine] = []


class PortalPayment(BaseModel):
    id: uuid.UUID
    status: str
    method: str
    amount: str
    allocated_amount: str
    unallocated_amount: str
    currency: str
    received_at: datetime


class PortalReceipt(BaseModel):
    id: uuid.UUID
    payment_id: uuid.UUID
    amount: str
    currency: str
    created_at: datetime


class PortalRefund(BaseModel):
    id: uuid.UUID
    payment_id: uuid.UUID
    amount: str
    currency: str
    status: str
    reason: str | None = None


class PortalCreditNote(BaseModel):
    id: uuid.UUID
    invoice_id: uuid.UUID
    amount: str
    currency: str
    status: str


class PortalCreditBalance(BaseModel):
    currency: str
    credit: str


class PortalAccessEvent(BaseModel):
    action: str
    resource_type: str
    resource_id: str
    occurred_at: datetime
    request_id: str | None = None


class PortalLinkEnroll(BaseModel):
    email: str = Field(max_length=254)
    patient_id: uuid.UUID
    display_name: str | None = Field(default=None, max_length=200)


class PortalLinkResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    patient_id: uuid.UUID
    status: str


class PortalWorkspaces(BaseModel):
    provider: bool
    portal: bool


class PortalOverview(BaseModel):
    display_name: str
    phone: str | None
    email: str | None
    date_of_birth: str | None = None
    is_active: bool
    last_visit_at: datetime | None = None
    next_appointment_at: datetime | None = None
    next_appointment_id: uuid.UUID | None = None
    outstanding_balance: str
    currency: str
    follow_up_due: str | None = None


class PortalTimelineItem(BaseModel):
    event_id: str
    kind: str
    category: str
    occurred_at: datetime
    title: str
    summary: str | None = None
    resource_type: str
    resource_id: uuid.UUID
    status: str | None = None


class PortalTimelinePage(BaseModel):
    items: list[PortalTimelineItem]
    next_cursor: str | None = None
