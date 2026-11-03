"""Billing models. Billing owns monetary truth; no floats, ever.

Tenant-owned financial documents with location scope; one global read-only
service catalog. Issued documents are immutable snapshots — corrections flow
through financial adjustment documents (refund / credit note), never through
mutation of issued rows. Patient credit is derived, never a separate ledger:
payment allocations always pin (tenant, patient) on both legs via composite
foreign keys, so cross-patient allocation is rejected by the database.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy import TIMESTAMP, Boolean, CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db import Base

# --- Lifecycles (single authority; service layer owns transitions) ---

ESTIMATE_DRAFT = "draft"
ESTIMATE_ISSUED = "issued"
ESTIMATE_CONVERTED = "converted"
ESTIMATE_EXPIRED = "expired"
ESTIMATE_CANCELLED = "cancelled"
ESTIMATE_STATUSES = (
    ESTIMATE_DRAFT,
    ESTIMATE_ISSUED,
    ESTIMATE_CONVERTED,
    ESTIMATE_EXPIRED,
    ESTIMATE_CANCELLED,
)

INVOICE_DRAFT = "draft"
INVOICE_ISSUED = "issued"
INVOICE_PARTIALLY_PAID = "partially_paid"
INVOICE_PAID = "paid"
INVOICE_VOIDED = "voided"
INVOICE_STATUSES = (
    INVOICE_DRAFT,
    INVOICE_ISSUED,
    INVOICE_PARTIALLY_PAID,
    INVOICE_PAID,
    INVOICE_VOIDED,
)

PAYMENT_RECORDED = "recorded"
PAYMENT_PARTIALLY_ALLOCATED = "partially_allocated"
PAYMENT_ALLOCATED = "allocated"
PAYMENT_PARTIALLY_REFUNDED = "partially_refunded"
PAYMENT_REFUNDED = "refunded"
PAYMENT_STATUSES = (
    PAYMENT_RECORDED,
    PAYMENT_PARTIALLY_ALLOCATED,
    PAYMENT_ALLOCATED,
    PAYMENT_PARTIALLY_REFUNDED,
    PAYMENT_REFUNDED,
)

REFUND_ISSUED = "issued"
REFUND_VOIDED = "voided"
REFUND_STATUSES = (REFUND_ISSUED, REFUND_VOIDED)

CREDIT_DRAFT = "draft"
CREDIT_ISSUED = "issued"
CREDIT_VOIDED = "voided"
CREDIT_STATUSES = (CREDIT_DRAFT, CREDIT_ISSUED, CREDIT_VOIDED)

TAX_TAXABLE = "taxable"
TAX_EXEMPT = "exempt"
TAX_ZERO_RATED = "zero_rated"
TAX_TREATMENTS = (TAX_TAXABLE, TAX_EXEMPT, TAX_ZERO_RATED)

DOC_INVOICE = "invoice"
DOC_RECEIPT = "receipt"
DOC_CREDIT_NOTE = "credit_note"
DOC_TYPES = (DOC_INVOICE, DOC_RECEIPT, DOC_CREDIT_NOTE)

INR = "INR"

MONEY = sa.Numeric(12, 2)
QTY = sa.Numeric(10, 2)
RATE = sa.Numeric(12, 2)
TAX_RATE = sa.Numeric(6, 2)


class ServiceCatalogItem(Base):
    """Global charge master. Reference data: no tenant, no RLS. Managed only
    through billing.config-gated endpoints (P4.2+); no other write paths.
    Rates are defaults captured into document lines as snapshots."""

    __tablename__ = "service_catalog"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    display: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    default_rate: Mapped[object] = mapped_column(RATE, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default=INR)
    hsn_sac: Mapped[str | None] = mapped_column(String(16), nullable=True)
    tax_rate: Mapped[object] = mapped_column(TAX_RATE, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (CheckConstraint("currency = 'INR'", name="ck_catalog_inr"),)


class Estimate(Base):
    """Non-binding cost proposal. Draft editable; issued frozen. Conversion
    snapshots selected lines into an invoice; the estimate never becomes the
    invoice. `treatment_plan_id` is a bare reference (no FK): billing must
    not depend on dental tables."""

    __tablename__ = "estimates"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False
    )
    encounter_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("encounters.id", ondelete="RESTRICT"), nullable=True
    )
    treatment_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    practitioner_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("practitioners.id", ondelete="RESTRICT"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        sa.Enum(
            *ESTIMATE_STATUSES, name="estimate_status", native_enum=True, validate_strings=True
        ),
        nullable=False,
        default=ESTIMATE_DRAFT,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("estimates.id", ondelete="RESTRICT"), nullable=True
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default=INR)
    subtotal: Mapped[object] = mapped_column(MONEY, nullable=False, default=0)
    tax_total: Mapped[object] = mapped_column(MONEY, nullable=False, default=0)
    grand_total: Mapped[object] = mapped_column(MONEY, nullable=False, default=0)
    valid_until: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    issued_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    issued_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_estimates_tenant", "tenant_id"),
        Index("ix_estimates_patient", "patient_id"),
        Index("ix_estimates_location", "location_id"),
        Index("ix_estimates_tenant_status", "tenant_id", "status"),
        Index("ix_estimates_plan", "treatment_plan_id"),
        CheckConstraint("currency = 'INR'", name="ck_estimates_inr"),
        CheckConstraint("subtotal >= 0", name="ck_estimates_subtotal_nn"),
        CheckConstraint("tax_total >= 0", name="ck_estimates_taxtotal_nn"),
        CheckConstraint("grand_total >= 0", name="ck_estimates_grand_nn"),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_estimates_tenant_idem",
        ),
    )


class EstimateLine(Base):
    """Proposal line. Editable while the parent is a draft; frozen (new
    estimate version instead of edits) once issued."""

    __tablename__ = "estimate_lines"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    estimate_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("estimates.id", ondelete="CASCADE"), nullable=False
    )
    service_catalog_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("service_catalog.id", ondelete="RESTRICT"), nullable=True
    )
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    quantity: Mapped[object] = mapped_column(QTY, nullable=False)
    unit_rate: Mapped[object] = mapped_column(RATE, nullable=False)
    discount_amount: Mapped[object] = mapped_column(MONEY, nullable=False, default=0)
    taxable_amount: Mapped[object] = mapped_column(MONEY, nullable=False, default=0)
    tax_rate: Mapped[object] = mapped_column(TAX_RATE, nullable=False, default=0)
    tax_amount: Mapped[object] = mapped_column(MONEY, nullable=False, default=0)
    hsn_sac: Mapped[str | None] = mapped_column(String(16), nullable=True)
    tax_treatment: Mapped[str] = mapped_column(String(16), nullable=False, default=TAX_TAXABLE)
    line_total: Mapped[object] = mapped_column(MONEY, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_estimate_lines_estimate", "estimate_id"),
        CheckConstraint("quantity > 0", name="ck_estlines_qty_pos"),
        CheckConstraint("unit_rate >= 0", name="ck_estlines_rate_nn"),
        CheckConstraint("discount_amount >= 0", name="ck_estlines_disc_nn"),
        CheckConstraint("taxable_amount >= 0", name="ck_estlines_taxable_nn"),
        CheckConstraint("tax_rate >= 0", name="ck_estlines_taxrate_nn"),
        CheckConstraint("tax_amount >= 0", name="ck_estlines_taxamt_nn"),
        CheckConstraint("line_total >= 0", name="ck_estlines_total_nn"),
        CheckConstraint(
            "tax_treatment IN ('taxable', 'exempt', 'zero_rated')",
            name="ck_estlines_taxtreat",
        ),
    )


class Invoice(Base):
    """Financial obligation. Draft editable; issued rows are immutable
    snapshots (lines carry copied prices/tax/HSN). Balances are derived from
    allocations + credit notes, never from a mutable paid_amount column."""

    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False
    )
    encounter_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("encounters.id", ondelete="RESTRICT"), nullable=True
    )
    source_estimate_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("estimates.id", ondelete="RESTRICT"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        sa.Enum(*INVOICE_STATUSES, name="invoice_status", native_enum=True, validate_strings=True),
        nullable=False,
        default=INVOICE_DRAFT,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default=INR)
    subtotal: Mapped[object] = mapped_column(MONEY, nullable=False, default=0)
    tax_total: Mapped[object] = mapped_column(MONEY, nullable=False, default=0)
    grand_total: Mapped[object] = mapped_column(MONEY, nullable=False, default=0)
    financial_year: Mapped[str | None] = mapped_column(String(16), nullable=True)
    doc_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    due_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    issued_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    issued_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    voided_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    void_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_invoices_tenant", "tenant_id"),
        Index("ix_invoices_patient", "patient_id"),
        Index("ix_invoices_location", "location_id"),
        Index("ix_invoices_tenant_status", "tenant_id", "status"),
        Index("ix_invoices_series", "tenant_id", "location_id", "financial_year"),
        sa.UniqueConstraint("id", "tenant_id", "patient_id", name="uq_invoices_id_tenant_patient"),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_invoices_tenant_idem",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "location_id",
            "financial_year",
            "doc_number",
            name="uq_invoices_series_number",
        ),
        CheckConstraint("currency = 'INR'", name="ck_invoices_inr"),
        CheckConstraint("subtotal >= 0", name="ck_invoices_subtotal_nn"),
        CheckConstraint("tax_total >= 0", name="ck_invoices_taxtotal_nn"),
        CheckConstraint("grand_total >= 0", name="ck_invoices_grand_nn"),
    )


class InvoiceLine(Base):
    """Issued-invoice line snapshot. Immutable once the parent is issued;
    corrections create adjustment documents, never edits. Each source
    estimate line converts at most once (`uq_invoice_lines_source_line_once`)."""

    __tablename__ = "invoice_lines"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    source_estimate_line_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("estimate_lines.id", ondelete="RESTRICT"), nullable=True
    )
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    quantity: Mapped[object] = mapped_column(QTY, nullable=False)
    unit_rate: Mapped[object] = mapped_column(RATE, nullable=False)
    discount_amount: Mapped[object] = mapped_column(MONEY, nullable=False, default=0)
    taxable_amount: Mapped[object] = mapped_column(MONEY, nullable=False, default=0)
    tax_rate: Mapped[object] = mapped_column(TAX_RATE, nullable=False, default=0)
    tax_amount: Mapped[object] = mapped_column(MONEY, nullable=False, default=0)
    hsn_sac: Mapped[str | None] = mapped_column(String(16), nullable=True)
    tax_treatment: Mapped[str] = mapped_column(String(16), nullable=False, default=TAX_TAXABLE)
    line_total: Mapped[object] = mapped_column(MONEY, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_invoice_lines_invoice", "invoice_id"),
        Index(
            "uq_invoice_lines_source_line_once",
            "source_estimate_line_id",
            unique=True,
            postgresql_where=sa.text("source_estimate_line_id IS NOT NULL"),
        ),
        CheckConstraint("quantity > 0", name="ck_invlines_qty_pos"),
        CheckConstraint("unit_rate >= 0", name="ck_invlines_rate_nn"),
        CheckConstraint("discount_amount >= 0", name="ck_invlines_disc_nn"),
        CheckConstraint("taxable_amount >= 0", name="ck_invlines_taxable_nn"),
        CheckConstraint("tax_rate >= 0", name="ck_invlines_taxrate_nn"),
        CheckConstraint("tax_amount >= 0", name="ck_invlines_taxamt_nn"),
        CheckConstraint("line_total >= 0", name="ck_invlines_total_nn"),
        CheckConstraint(
            "tax_treatment IN ('taxable', 'exempt', 'zero_rated')",
            name="ck_invlines_taxtreat",
        ),
    )


class Payment(Base):
    """Money received. Immutable receipt of funds; application to invoices
    happens only through allocation rows. `provider_data` is opaque JSONB
    (never queryable facts)."""

    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False
    )
    encounter_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("encounters.id", ondelete="RESTRICT"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        sa.Enum(*PAYMENT_STATUSES, name="payment_status", native_enum=True, validate_strings=True),
        nullable=False,
        default=PAYMENT_RECORDED,
    )
    amount: Mapped[object] = mapped_column(MONEY, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default=INR)
    method: Mapped[str] = mapped_column(String(32), nullable=False)
    received_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    provider_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_payments_tenant", "tenant_id"),
        Index("ix_payments_patient", "patient_id"),
        Index("ix_payments_location", "location_id"),
        Index("ix_payments_tenant_status", "tenant_id", "status"),
        sa.UniqueConstraint("id", "tenant_id", "patient_id", name="uq_payments_id_tenant_patient"),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_payments_tenant_idem",
        ),
        CheckConstraint("currency = 'INR'", name="ck_payments_inr"),
        CheckConstraint("amount >= 0", name="ck_payments_amount_nn"),
    )


class PaymentAllocation(Base):
    """Application of received money to an invoice. Immutable; reversal is a
    new reversing row (at most one per forward row). The composite FKs pin
    (tenant, patient) on both legs, so the database rejects cross-tenant
    and cross-patient allocation. `idempotency_key` records the allocate
    request identity (lock-scoped exact-set replay, never unique)."""

    __tablename__ = "payment_allocations"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False
    )
    payment_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    invoice_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    amount: Mapped[object] = mapped_column(MONEY, nullable=False)
    reversal_of_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("payment_allocations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_allocations_payment", "payment_id"),
        Index("ix_allocations_invoice", "invoice_id"),
        Index("ix_allocations_tenant", "tenant_id"),
        Index(
            "uq_alloc_reversal_once",
            "reversal_of_id",
            unique=True,
            postgresql_where=sa.text("reversal_of_id IS NOT NULL"),
        ),
        sa.ForeignKeyConstraint(
            ["payment_id", "tenant_id", "patient_id"],
            ["payments.id", "payments.tenant_id", "payments.patient_id"],
            ondelete="CASCADE",
            name="fk_alloc_payment_match",
        ),
        sa.ForeignKeyConstraint(
            ["invoice_id", "tenant_id", "patient_id"],
            ["invoices.id", "invoices.tenant_id", "invoices.patient_id"],
            ondelete="RESTRICT",
            name="fk_alloc_invoice_match",
        ),
        CheckConstraint("amount > 0", name="ck_alloc_amount_pos"),
    )


class Refund(Base):
    """Money returned against a payment. Immutable once issued; capped at the
    refundable remainder; the original payment row is never mutated."""

    __tablename__ = "refunds"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False
    )
    payment_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        sa.Enum(*REFUND_STATUSES, name="refund_status", native_enum=True, validate_strings=True),
        nullable=False,
        default=REFUND_ISSUED,
    )
    amount: Mapped[object] = mapped_column(MONEY, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default=INR)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_refunds_tenant", "tenant_id"),
        Index("ix_refunds_payment", "payment_id"),
        sa.ForeignKeyConstraint(
            ["payment_id", "tenant_id", "patient_id"],
            ["payments.id", "payments.tenant_id", "payments.patient_id"],
            ondelete="RESTRICT",
            name="fk_refund_payment_match",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_refunds_tenant_idem",
        ),
        CheckConstraint("currency = 'INR'", name="ck_refunds_inr"),
        CheckConstraint("amount > 0", name="ck_refunds_amount_pos"),
        CheckConstraint("char_length(reason) >= 2", name="ck_refunds_reason_len"),
    )


class CreditNote(Base):
    """Financial adjustment against exactly one issued invoice. Draft is
    editable only in the narrow void sense (drafts are unnumbered and
    affect no balance); issued notes are immutable, numbered,
    tax-snapshotted, and never rewrite the invoice."""

    __tablename__ = "credit_notes"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    invoice_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.Enum(
            *CREDIT_STATUSES, name="credit_note_status", native_enum=True, validate_strings=True
        ),
        nullable=False,
        default=CREDIT_DRAFT,
    )
    amount: Mapped[object] = mapped_column(MONEY, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default=INR)
    tax_rate: Mapped[object] = mapped_column(TAX_RATE, nullable=False, default=0)
    tax_amount: Mapped[object] = mapped_column(MONEY, nullable=False, default=0)
    hsn_sac: Mapped[str | None] = mapped_column(String(16), nullable=True)
    tax_treatment: Mapped[str] = mapped_column(String(16), nullable=False, default=TAX_TAXABLE)
    financial_year: Mapped[str | None] = mapped_column(String(16), nullable=True)
    doc_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_credit_notes_tenant", "tenant_id"),
        Index("ix_credit_notes_invoice", "invoice_id"),
        Index("ix_credit_notes_series", "tenant_id", "location_id", "financial_year"),
        sa.ForeignKeyConstraint(
            ["patient_id"], ["patients.id"], ondelete="RESTRICT", name="fk_credit_patient"
        ),
        sa.ForeignKeyConstraint(
            ["invoice_id", "tenant_id", "patient_id"],
            ["invoices.id", "invoices.tenant_id", "invoices.patient_id"],
            ondelete="RESTRICT",
            name="fk_credit_invoice_match",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_credit_notes_tenant_idem",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "location_id",
            "financial_year",
            "doc_number",
            name="uq_credit_notes_series_number",
        ),
        CheckConstraint("currency = 'INR'", name="ck_credit_notes_inr"),
        CheckConstraint("amount > 0", name="ck_credit_notes_amount_pos"),
        CheckConstraint("tax_rate >= 0", name="ck_credit_notes_taxrate_nn"),
        CheckConstraint("tax_amount >= 0", name="ck_credit_notes_taxamt_nn"),
        CheckConstraint("char_length(reason) >= 2", name="ck_credit_notes_reason_len"),
        CheckConstraint(
            "tax_treatment IN ('taxable', 'exempt', 'zero_rated')",
            name="ck_credit_notes_taxtreat",
        ),
    )


class Receipt(Base):
    """Evidence of payment. 1:1 with payment in P4; payment remains the
    financial source of truth. Immutable; rendered output is deferred."""

    __tablename__ = "receipts"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False
    )
    payment_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False
    )
    amount: Mapped[object] = mapped_column(MONEY, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default=INR)
    financial_year: Mapped[str | None] = mapped_column(String(16), nullable=True)
    doc_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_receipts_tenant", "tenant_id"),
        Index("ix_receipts_series", "tenant_id", "location_id", "financial_year"),
        sa.ForeignKeyConstraint(
            ["payment_id", "tenant_id", "patient_id"],
            ["payments.id", "payments.tenant_id", "payments.patient_id"],
            ondelete="RESTRICT",
            name="fk_receipt_payment_match",
        ),
        sa.UniqueConstraint("payment_id", name="uq_receipts_payment_once"),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_receipts_tenant_idem",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "location_id",
            "financial_year",
            "doc_number",
            name="uq_receipts_series_number",
        ),
        CheckConstraint("currency = 'INR'", name="ck_receipts_inr"),
        CheckConstraint("amount >= 0", name="ck_receipts_amount_nn"),
    )
