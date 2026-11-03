"""Billing schemas. Shape validation only; money math lives in money.py,
lifecycle rules in the service layer. Money serializes as strings so JSON
transport never passes through binary floating point."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ServiceCatalogCreateRequest(BaseModel):
    code: str = Field(max_length=40)
    display: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    default_rate: Decimal = Field(default=Decimal("0"))
    currency: str = Field(default="INR", max_length=3)
    hsn_sac: str | None = Field(default=None, max_length=16)
    tax_rate: Decimal = Field(default=Decimal("0"))


class ServiceCatalogUpdateRequest(BaseModel):
    display: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    default_rate: Decimal | None = None
    tax_rate: Decimal | None = None
    hsn_sac: str | None = Field(default=None, max_length=16)
    currency: str | None = Field(default=None, max_length=3)


class ServiceCatalogResponse(BaseModel):
    id: uuid.UUID
    code: str
    display: str
    description: str | None
    default_rate: str
    currency: str
    hsn_sac: str | None
    tax_rate: str
    is_active: bool


class ServiceCatalogListResponse(BaseModel):
    items: list[ServiceCatalogResponse]
    next_cursor: uuid.UUID | None


class EstimateLineRequest(BaseModel):
    service_catalog_id: uuid.UUID | None = None
    description: str | None = Field(default=None, max_length=300)
    quantity: Decimal = Field(default=Decimal("1"))
    unit_rate: Decimal | None = None
    discount_amount: Decimal = Field(default=Decimal("0"))
    tax_rate: Decimal | None = None
    hsn_sac: str | None = Field(default=None, max_length=16)
    tax_treatment: str | None = None
    sequence: int = Field(default=1, ge=1, le=500)


class EstimateCreateRequest(BaseModel):
    patient_id: uuid.UUID
    location_id: uuid.UUID
    practitioner_id: uuid.UUID | None = None
    encounter_id: uuid.UUID | None = None
    treatment_plan_id: uuid.UUID | None = None
    valid_until: date | None = None
    notes: str | None = Field(default=None, max_length=500)
    idempotency_key: str | None = Field(default=None, max_length=64)
    items: list[EstimateLineRequest] = Field(default_factory=list, max_length=100)


class EstimateUpdateRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=500)
    valid_until: date | None = None


class EstimateLineUpdateRequest(BaseModel):
    description: str | None = Field(default=None, max_length=300)
    quantity: Decimal | None = None
    unit_rate: Decimal | None = None
    discount_amount: Decimal | None = None
    tax_rate: Decimal | None = None
    hsn_sac: str | None = Field(default=None, max_length=16)
    tax_treatment: str | None = None
    sequence: int | None = Field(default=None, ge=1, le=500)


class EstimateLineResponse(BaseModel):
    id: uuid.UUID
    service_catalog_id: uuid.UUID | None
    description: str
    quantity: str
    unit_rate: str
    discount_amount: str
    taxable_amount: str
    tax_rate: str
    tax_amount: str
    hsn_sac: str | None
    tax_treatment: str
    line_total: str
    sequence: int


class EstimateResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    location_id: uuid.UUID
    patient_id: uuid.UUID
    encounter_id: uuid.UUID | None
    treatment_plan_id: uuid.UUID | None
    practitioner_id: uuid.UUID | None
    status: str
    version: int
    currency: str
    subtotal: str
    tax_total: str
    grand_total: str
    valid_until: date | None
    notes: str | None
    lines: list[EstimateLineResponse]
    created_at: datetime
    updated_at: datetime


class EstimateListResponse(BaseModel):
    items: list[EstimateResponse]
    next_cursor: uuid.UUID | None


class InvoiceLineRequest(BaseModel):
    service_catalog_id: uuid.UUID | None = None
    description: str | None = Field(default=None, max_length=300)
    quantity: Decimal = Field(default=Decimal("1"))
    unit_rate: Decimal | None = None
    discount_amount: Decimal = Field(default=Decimal("0"))
    tax_rate: Decimal | None = None
    hsn_sac: str | None = Field(default=None, max_length=16)
    tax_treatment: str | None = None
    sequence: int = Field(default=1, ge=1, le=500)


class InvoiceCreateRequest(BaseModel):
    patient_id: uuid.UUID
    location_id: uuid.UUID
    encounter_id: uuid.UUID | None = None
    due_date: date | None = None
    notes: str | None = Field(default=None, max_length=500)
    currency: str = Field(default="INR", max_length=3)
    idempotency_key: str | None = Field(default=None, max_length=64)
    items: list[InvoiceLineRequest] = Field(default_factory=list, max_length=100)


class InvoiceUpdateRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=500)
    due_date: date | None = None
    clear_due_date: bool = False


class InvoiceLineUpdateRequest(BaseModel):
    description: str | None = Field(default=None, max_length=300)
    quantity: Decimal | None = None
    unit_rate: Decimal | None = None
    discount_amount: Decimal | None = None
    tax_rate: Decimal | None = None
    hsn_sac: str | None = Field(default=None, max_length=16)
    tax_treatment: str | None = None
    sequence: int | None = Field(default=None, ge=1, le=500)


class InvoiceVoidRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=200)


class ConvertEstimateRequest(BaseModel):
    line_ids: list[uuid.UUID] | None = None
    due_date: date | None = None
    notes: str | None = Field(default=None, max_length=500)
    idempotency_key: str | None = Field(default=None, max_length=64)


class InvoiceLineResponse(BaseModel):
    id: uuid.UUID
    source_estimate_line_id: uuid.UUID | None
    description: str
    quantity: str
    unit_rate: str
    discount_amount: str
    taxable_amount: str
    tax_rate: str
    tax_amount: str
    hsn_sac: str | None
    tax_treatment: str
    line_total: str
    sequence: int


class InvoiceResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    location_id: uuid.UUID
    patient_id: uuid.UUID
    encounter_id: uuid.UUID | None
    source_estimate_id: uuid.UUID | None
    status: str
    version: int
    currency: str
    subtotal: str
    tax_total: str
    grand_total: str
    allocated_amount: str
    outstanding_amount: str
    financial_year: str | None
    doc_number: int | None
    due_date: date | None
    notes: str | None
    lines: list[InvoiceLineResponse]
    created_at: datetime
    updated_at: datetime


class InvoiceListResponse(BaseModel):
    items: list[InvoiceResponse]
    next_cursor: uuid.UUID | None


class PaymentCreateRequest(BaseModel):
    patient_id: uuid.UUID
    location_id: uuid.UUID
    encounter_id: uuid.UUID | None = None
    method: str
    amount: Decimal
    currency: str = Field(default="INR", max_length=3)
    received_at: datetime | None = None
    provider_ref: str | None = Field(default=None, max_length=128)
    provider_data: dict[str, object] | None = None
    idempotency_key: str | None = Field(default=None, max_length=64)


class AllocationItemRequest(BaseModel):
    invoice_id: uuid.UUID
    amount: Decimal


class AllocateRequest(BaseModel):
    allocations: list[AllocationItemRequest] = Field(min_length=1, max_length=50)
    idempotency_key: str | None = Field(default=None, max_length=64)


class ReverseAllocationRequest(BaseModel):
    reason: str = Field(min_length=2, max_length=200)


class PaymentResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    location_id: uuid.UUID
    patient_id: uuid.UUID
    encounter_id: uuid.UUID | None
    status: str
    method: str
    amount: str
    allocated_amount: str
    unallocated_amount: str
    currency: str
    received_at: datetime
    provider_ref: str | None
    created_at: datetime
    updated_at: datetime


class PaymentListResponse(BaseModel):
    items: list[PaymentResponse]
    next_cursor: uuid.UUID | None


class AllocationResponse(BaseModel):
    id: uuid.UUID
    payment_id: uuid.UUID
    invoice_id: uuid.UUID
    amount: str
    reversal_of_id: uuid.UUID | None
    reversed: bool
    idempotency_key: str | None


class AllocationListResponse(BaseModel):
    items: list[AllocationResponse]


class InvoiceBalanceResponse(BaseModel):
    invoice_id: uuid.UUID
    status: str
    grand_total: str
    allocated_amount: str
    outstanding_amount: str


class PatientCreditResponse(BaseModel):
    patient_id: uuid.UUID
    credit_amount: str


class RefundCreateRequest(BaseModel):
    amount: Decimal
    reason: str = Field(min_length=2, max_length=200)
    invoice_id: uuid.UUID | None = None
    idempotency_key: str | None = Field(default=None, max_length=64)


class RefundResponse(BaseModel):
    id: uuid.UUID
    payment_id: uuid.UUID
    invoice_id: uuid.UUID | None
    status: str
    amount: str
    currency: str
    reason: str
    created_at: datetime
    updated_at: datetime


class RefundListResponse(BaseModel):
    items: list[RefundResponse]


class CreditNoteCreateRequest(BaseModel):
    amount: Decimal
    reason: str = Field(min_length=2, max_length=200)
    tax_rate: Decimal | None = None
    tax_amount: Decimal | None = None
    hsn_sac: str | None = Field(default=None, max_length=16)
    tax_treatment: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=64)


class CreditNoteVoidRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=200)


class CreditNoteResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    location_id: uuid.UUID
    patient_id: uuid.UUID
    invoice_id: uuid.UUID
    status: str
    amount: str
    currency: str
    tax_rate: str
    tax_amount: str
    hsn_sac: str | None
    tax_treatment: str
    financial_year: str | None
    doc_number: int | None
    reason: str
    created_at: datetime
    updated_at: datetime


class CreditNoteListResponse(BaseModel):
    items: list[CreditNoteResponse]


class ReceiptCreateRequest(BaseModel):
    idempotency_key: str | None = Field(default=None, max_length=64)


class ReceiptResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    location_id: uuid.UUID
    patient_id: uuid.UUID
    payment_id: uuid.UUID
    amount: str
    currency: str
    financial_year: str | None
    doc_number: int | None
    created_at: datetime
