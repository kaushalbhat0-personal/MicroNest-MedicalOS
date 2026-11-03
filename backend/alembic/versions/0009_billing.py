"""0009 billing foundation: service catalog + estimates/invoices/payments/
allocations/refunds/credit notes/receipts.

Global service catalog (reference data, no RLS). Unlike P3 read-only
catalogs, P4.2 manages it through billing.config-gated endpoints, so the app
role holds full CRUD (still no RLS: no tenant_id; permission gates are the
access control). All financial documents are tenant-owned, RLS-enforced,
least-privilege granted.
Patient credit is derived (no ledger table): allocations pin
(tenant, patient) on both legs via composite FKs, so cross-patient
allocation is rejected by the database.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0009_billing"
down_revision: str | Sequence[str] | None = "0008_clinical"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "hos_app"
SETTING = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"

# Seed permission bundles (must match platform/authz/permissions.py).
CLINICAL_ADMIN = [
    "encounter.open",
    "encounter.close",
    "encounter.read",
    "clinical.read",
    "clinical.create",
    "prescription.read",
    "prescription.create",
    "prescription.sign",
    "dental.read",
    "dental.record",
    "plan.manage",
]
BILLING_FULL = [
    "billing.read",
    "billing.create",
    "invoice.issue",
    "payment.record",
    "billing.refund",
    "billing.config",
]
BASE_TENANT_ADMIN = [
    "tenant.read",
    "settings.manage",
    "staff.invite",
    "staff.manage",
    "roles.manage",
    "locations.manage",
    "audit.read",
    "appointment.read",
    "appointment.create",
    "appointment.update",
    "patient.read",
    "patient.create",
]
ROLE_PERMS = {
    "tenant_admin": BASE_TENANT_ADMIN + CLINICAL_ADMIN + BILLING_FULL,
    "doctor": ["tenant.read", "appointment.read", "appointment.update", "patient.read"]
    + CLINICAL_ADMIN
    + ["billing.read", "billing.create"],
    "receptionist": [
        "tenant.read",
        "appointment.read",
        "appointment.create",
        "appointment.update",
        "patient.read",
        "patient.create",
        "encounter.open",
        "encounter.read",
        "billing.read",
        "payment.record",
    ],
    "nurse": [
        "tenant.read",
        "appointment.read",
        "patient.read",
        "encounter.read",
        "clinical.read",
        "clinical.create",
    ],
    "accountant": ["tenant.read"] + BILLING_FULL,
    "staff": ["tenant.read"],
    "patient": [],
    "platform_admin": ["platform.tenant.create", "platform.tenant.suspend", "platform.health"],
}

# Frozen P3 bundles (downgrade path only).
P3_PERMS = {
    "tenant_admin": BASE_TENANT_ADMIN + CLINICAL_ADMIN,
    "doctor": ["tenant.read", "appointment.read", "appointment.update", "patient.read"]
    + CLINICAL_ADMIN,
    "receptionist": [
        "tenant.read",
        "appointment.read",
        "appointment.create",
        "appointment.update",
        "patient.read",
        "patient.create",
        "encounter.open",
        "encounter.read",
    ],
    "nurse": [
        "tenant.read",
        "appointment.read",
        "patient.read",
        "encounter.read",
        "clinical.read",
        "clinical.create",
    ],
    "accountant": ["tenant.read"],
    "staff": ["tenant.read"],
    "patient": [],
    "platform_admin": ["platform.tenant.create", "platform.tenant.suspend", "platform.health"],
}


def _enums() -> dict[str, postgresql.ENUM]:
    return {
        "estimate_status": postgresql.ENUM(
            "draft", "issued", "converted", "expired", "cancelled", name="estimate_status"
        ),
        "invoice_status": postgresql.ENUM(
            "draft", "issued", "partially_paid", "paid", "voided", name="invoice_status"
        ),
        "payment_status": postgresql.ENUM(
            "recorded",
            "partially_allocated",
            "allocated",
            "partially_refunded",
            "refunded",
            name="payment_status",
        ),
        "refund_status": postgresql.ENUM("issued", "voided", name="refund_status"),
        "credit_note_status": postgresql.ENUM("issued", "voided", name="credit_note_status"),
    }


TENANT_TABLES = [
    "estimates",
    "estimate_lines",
    "invoices",
    "invoice_lines",
    "payments",
    "payment_allocations",
    "refunds",
    "credit_notes",
    "receipts",
]

CATALOG_TABLES = [
    "service_catalog",
]


def upgrade() -> None:
    E = _enums()

    # --- Global read-only service catalog (reference data, no RLS) ---
    op.create_table(
        "service_catalog",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("display", sa.String(200), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("default_rate", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("hsn_sac", sa.String(16), nullable=True),
        sa.Column("tax_rate", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        sa.CheckConstraint("currency = 'INR'", name="ck_catalog_inr"),
    )

    # --- Estimates ---
    op.create_table(
        "estimates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("treatment_plan_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("practitioner_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", E["estimate_status"], nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("tax_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("grand_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("idempotency_key", sa.String(64), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("issued_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("issued_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["encounter_id"], ["encounters.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["practitioner_id"], ["practitioners.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supersedes_id"], ["estimates.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_estimates_tenant_idem"),
        sa.CheckConstraint("currency = 'INR'", name="ck_estimates_inr"),
        sa.CheckConstraint("subtotal >= 0", name="ck_estimates_subtotal_nn"),
        sa.CheckConstraint("tax_total >= 0", name="ck_estimates_taxtotal_nn"),
        sa.CheckConstraint("grand_total >= 0", name="ck_estimates_grand_nn"),
    )
    op.create_index("ix_estimates_tenant", "estimates", ["tenant_id"])
    op.create_index("ix_estimates_patient", "estimates", ["patient_id"])
    op.create_index("ix_estimates_location", "estimates", ["location_id"])
    op.create_index("ix_estimates_tenant_status", "estimates", ["tenant_id", "status"])
    op.create_index("ix_estimates_plan", "estimates", ["treatment_plan_id"])

    op.create_table(
        "estimate_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("estimate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_catalog_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=False),
        sa.Column("unit_rate", sa.Numeric(12, 2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("taxable_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("tax_rate", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("tax_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("hsn_sac", sa.String(16), nullable=True),
        sa.Column("tax_treatment", sa.String(16), nullable=False, server_default="taxable"),
        sa.Column("line_total", sa.Numeric(12, 2), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["estimate_id"], ["estimates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["service_catalog_id"], ["service_catalog.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("quantity > 0", name="ck_estlines_qty_pos"),
        sa.CheckConstraint("unit_rate >= 0", name="ck_estlines_rate_nn"),
        sa.CheckConstraint("discount_amount >= 0", name="ck_estlines_disc_nn"),
        sa.CheckConstraint("taxable_amount >= 0", name="ck_estlines_taxable_nn"),
        sa.CheckConstraint("tax_rate >= 0", name="ck_estlines_taxrate_nn"),
        sa.CheckConstraint("tax_amount >= 0", name="ck_estlines_taxamt_nn"),
        sa.CheckConstraint("line_total >= 0", name="ck_estlines_total_nn"),
        sa.CheckConstraint(
            "tax_treatment IN ('taxable', 'exempt', 'zero_rated')", name="ck_estlines_taxtreat"
        ),
    )
    op.create_index("ix_estimate_lines_estimate", "estimate_lines", ["estimate_id"])

    # --- Invoices ---
    op.create_table(
        "invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_estimate_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", E["invoice_status"], nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("tax_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("grand_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("financial_year", sa.String(16), nullable=True),
        sa.Column("doc_number", sa.Integer(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("idempotency_key", sa.String(64), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("issued_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("issued_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("voided_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("voided_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("void_reason", sa.String(200), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["encounter_id"], ["encounters.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_estimate_id"], ["estimates.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "tenant_id", "patient_id", name="uq_invoices_id_tenant_patient"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_invoices_tenant_idem"),
        sa.UniqueConstraint(
            "tenant_id",
            "location_id",
            "financial_year",
            "doc_number",
            name="uq_invoices_series_number",
        ),
        sa.CheckConstraint("currency = 'INR'", name="ck_invoices_inr"),
        sa.CheckConstraint("subtotal >= 0", name="ck_invoices_subtotal_nn"),
        sa.CheckConstraint("tax_total >= 0", name="ck_invoices_taxtotal_nn"),
        sa.CheckConstraint("grand_total >= 0", name="ck_invoices_grand_nn"),
    )
    op.create_index("ix_invoices_tenant", "invoices", ["tenant_id"])
    op.create_index("ix_invoices_patient", "invoices", ["patient_id"])
    op.create_index("ix_invoices_location", "invoices", ["location_id"])
    op.create_index("ix_invoices_tenant_status", "invoices", ["tenant_id", "status"])
    op.create_index(
        "ix_invoices_series", "invoices", ["tenant_id", "location_id", "financial_year"]
    )

    op.create_table(
        "invoice_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_estimate_line_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=False),
        sa.Column("unit_rate", sa.Numeric(12, 2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("taxable_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("tax_rate", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("tax_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("hsn_sac", sa.String(16), nullable=True),
        sa.Column("tax_treatment", sa.String(16), nullable=False, server_default="taxable"),
        sa.Column("line_total", sa.Numeric(12, 2), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_estimate_line_id"], ["estimate_lines.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("quantity > 0", name="ck_invlines_qty_pos"),
        sa.CheckConstraint("unit_rate >= 0", name="ck_invlines_rate_nn"),
        sa.CheckConstraint("discount_amount >= 0", name="ck_invlines_disc_nn"),
        sa.CheckConstraint("taxable_amount >= 0", name="ck_invlines_taxable_nn"),
        sa.CheckConstraint("tax_rate >= 0", name="ck_invlines_taxrate_nn"),
        sa.CheckConstraint("tax_amount >= 0", name="ck_invlines_taxamt_nn"),
        sa.CheckConstraint("line_total >= 0", name="ck_invlines_total_nn"),
        sa.CheckConstraint(
            "tax_treatment IN ('taxable', 'exempt', 'zero_rated')", name="ck_invlines_taxtreat"
        ),
    )
    op.create_index("ix_invoice_lines_invoice", "invoice_lines", ["invoice_id"])

    # --- Payments ---
    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", E["payment_status"], nullable=False, server_default="recorded"),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("method", sa.String(32), nullable=False),
        sa.Column("received_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("provider_ref", sa.String(128), nullable=True),
        sa.Column("provider_data", postgresql.JSONB(), nullable=True),
        sa.Column("idempotency_key", sa.String(64), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["encounter_id"], ["encounters.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "tenant_id", "patient_id", name="uq_payments_id_tenant_patient"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_payments_tenant_idem"),
        sa.CheckConstraint("currency = 'INR'", name="ck_payments_inr"),
        sa.CheckConstraint("amount >= 0", name="ck_payments_amount_nn"),
    )
    op.create_index("ix_payments_tenant", "payments", ["tenant_id"])
    op.create_index("ix_payments_patient", "payments", ["patient_id"])
    op.create_index("ix_payments_location", "payments", ["location_id"])
    op.create_index("ix_payments_tenant_status", "payments", ["tenant_id", "status"])

    # --- Allocations (composite FKs pin tenant+patient on both legs) ---
    op.create_table(
        "payment_allocations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("reversal_of_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="RESTRICT"),
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
        sa.ForeignKeyConstraint(
            ["reversal_of_id"], ["payment_allocations.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("amount > 0", name="ck_alloc_amount_pos"),
    )
    op.create_index("ix_allocations_payment", "payment_allocations", ["payment_id"])
    op.create_index("ix_allocations_invoice", "payment_allocations", ["invoice_id"])
    op.create_index("ix_allocations_tenant", "payment_allocations", ["tenant_id"])

    # --- Refunds ---
    op.create_table(
        "refunds",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", E["refund_status"], nullable=False, server_default="issued"),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("reason", sa.String(200), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["payment_id", "tenant_id", "patient_id"],
            ["payments.id", "payments.tenant_id", "payments.patient_id"],
            ondelete="RESTRICT",
            name="fk_refund_payment_match",
        ),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_refunds_tenant_idem"),
        sa.CheckConstraint("currency = 'INR'", name="ck_refunds_inr"),
        sa.CheckConstraint("amount > 0", name="ck_refunds_amount_pos"),
        sa.CheckConstraint("char_length(reason) >= 2", name="ck_refunds_reason_len"),
    )
    op.create_index("ix_refunds_tenant", "refunds", ["tenant_id"])
    op.create_index("ix_refunds_payment", "refunds", ["payment_id"])

    # --- Credit notes ---
    op.create_table(
        "credit_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", E["credit_note_status"], nullable=False, server_default="issued"),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("tax_rate", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("tax_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("hsn_sac", sa.String(16), nullable=True),
        sa.Column("tax_treatment", sa.String(16), nullable=False, server_default="taxable"),
        sa.Column("financial_year", sa.String(16), nullable=True),
        sa.Column("doc_number", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(200), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["invoice_id", "tenant_id", "patient_id"],
            ["invoices.id", "invoices.tenant_id", "invoices.patient_id"],
            ondelete="RESTRICT",
            name="fk_credit_invoice_match",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_credit_notes_tenant_idem"),
        sa.UniqueConstraint(
            "tenant_id",
            "location_id",
            "financial_year",
            "doc_number",
            name="uq_credit_notes_series_number",
        ),
        sa.CheckConstraint("currency = 'INR'", name="ck_credit_notes_inr"),
        sa.CheckConstraint("amount > 0", name="ck_credit_notes_amount_pos"),
        sa.CheckConstraint("tax_rate >= 0", name="ck_credit_notes_taxrate_nn"),
        sa.CheckConstraint("tax_amount >= 0", name="ck_credit_notes_taxamt_nn"),
        sa.CheckConstraint("char_length(reason) >= 2", name="ck_credit_notes_reason_len"),
        sa.CheckConstraint(
            "tax_treatment IN ('taxable', 'exempt', 'zero_rated')",
            name="ck_credit_notes_taxtreat",
        ),
    )
    op.create_index("ix_credit_notes_tenant", "credit_notes", ["tenant_id"])
    op.create_index("ix_credit_notes_invoice", "credit_notes", ["invoice_id"])
    op.create_index(
        "ix_credit_notes_series", "credit_notes", ["tenant_id", "location_id", "financial_year"]
    )

    # --- Receipts (1:1 with payment) ---
    op.create_table(
        "receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("financial_year", sa.String(16), nullable=True),
        sa.Column("doc_number", sa.Integer(), nullable=True),
        sa.Column("idempotency_key", sa.String(64), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["payment_id", "tenant_id", "patient_id"],
            ["payments.id", "payments.tenant_id", "payments.patient_id"],
            ondelete="RESTRICT",
            name="fk_receipt_payment_match",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_id", name="uq_receipts_payment_once"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_receipts_tenant_idem"),
        sa.UniqueConstraint(
            "tenant_id",
            "location_id",
            "financial_year",
            "doc_number",
            name="uq_receipts_series_number",
        ),
        sa.CheckConstraint("currency = 'INR'", name="ck_receipts_inr"),
        sa.CheckConstraint("amount >= 0", name="ck_receipts_amount_nn"),
    )
    op.create_index("ix_receipts_tenant", "receipts", ["tenant_id"])
    op.create_index(
        "ix_receipts_series", "receipts", ["tenant_id", "location_id", "financial_year"]
    )

    # --- Seed role bundles grow P4 billing permissions ---
    import json as _json

    for name, perms in ROLE_PERMS.items():
        op.execute(
            sa.text(
                "UPDATE roles SET permissions = CAST(:perms AS JSONB) "
                "WHERE tenant_id IS NULL AND name = :name"
            ).bindparams(name=name, perms=_json.dumps(sorted(perms)))
        )

    # --- Grants + RLS ---
    # service_catalog is global (no tenant_id → no RLS), but unlike P3
    # read-only catalogs it is managed via billing.config-gated endpoints,
    # so the app role needs full CRUD; permission checks are the control.
    op.execute(sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON service_catalog TO {APP_ROLE}"))
    for table in CATALOG_TABLES:
        if table != "service_catalog":
            op.execute(sa.text(f"GRANT SELECT ON {table} TO {APP_ROLE}"))
    for table in TENANT_TABLES:
        op.execute(sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}"))
    op.execute(sa.text(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}"))
    for table in TENANT_TABLES:
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                f"CREATE POLICY {table}_tenant_isolation ON {table} "
                f"FOR ALL TO {APP_ROLE} USING (tenant_id = {SETTING}) "
                f"WITH CHECK (tenant_id = {SETTING})"
            )
        )


def downgrade() -> None:
    import json as _json

    for name, perms in P3_PERMS.items():
        op.execute(
            sa.text(
                "UPDATE roles SET permissions = CAST(:perms AS JSONB) "
                "WHERE tenant_id IS NULL AND name = :name"
            ).bindparams(name=name, perms=_json.dumps(sorted(perms)))
        )
    for table in TENANT_TABLES:
        op.execute(sa.text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
        op.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))
    for table in reversed(TENANT_TABLES):
        op.execute(sa.text(f"DROP TABLE {table}"))
    for table in CATALOG_TABLES:
        op.execute(sa.text(f"DROP TABLE {table}"))
    for enum_name in (
        "estimate_status",
        "invoice_status",
        "payment_status",
        "refund_status",
        "credit_note_status",
    ):
        postgresql.ENUM(name=enum_name).drop(op.get_bind(), checkfirst=True)
