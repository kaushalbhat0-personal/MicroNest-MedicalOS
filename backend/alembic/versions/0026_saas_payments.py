"""0026 P2.4 SaaS payment transactions + webhook inbox (Razorpay/mock).

Separate from clinic-to-patient billing tables. RLS on tenant-scoped rows.
Webhook inbox is platform-scoped (no tenant JWT on ingest).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026_saas_payments"
down_revision: str | Sequence[str] | None = "0025_commercial_gates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "saas_customers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_customer_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "provider", name="uq_saas_customers_tenant_provider"),
        sa.UniqueConstraint(
            "provider", "provider_customer_id", name="uq_saas_customers_provider_ref"
        ),
    )
    op.create_table(
        "saas_payment_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "subscription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subscriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subscription_plans.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="INR"),
        sa.Column("billing_interval", sa.String(16), nullable=True),
        sa.Column("provider_order_id", sa.Text(), nullable=True),
        sa.Column("provider_payment_id", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False, server_default="checkout"),
        sa.Column("period_start", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("period_end", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("paid_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_saas_txn_tenant_idempotency"
        ),
        sa.CheckConstraint(
            "status IN ('pending','paid','failed','refunded','cancelled')",
            name="ck_saas_txn_status",
        ),
        sa.CheckConstraint("amount_minor >= 0", name="ck_saas_txn_amount"),
        sa.CheckConstraint("currency = 'INR'", name="ck_saas_txn_currency"),
    )
    op.create_index(
        "ix_saas_txn_tenant_created",
        "saas_payment_transactions",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_saas_txn_provider_order",
        "saas_payment_transactions",
        ["provider", "provider_order_id"],
    )

    op.create_table(
        "saas_webhook_inbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_event_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="received"),
        sa.Column("payload_digest", sa.Text(), nullable=False),
        sa.Column(
            "related_transaction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("saas_payment_transactions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("received_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("processed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "provider", "provider_event_id", name="uq_saas_webhook_provider_event"
        ),
        sa.CheckConstraint(
            "status IN ('received','processed','failed','ignored','duplicate')",
            name="ck_saas_webhook_status",
        ),
    )
    op.create_index(
        "ix_saas_webhook_status", "saas_webhook_inbox", ["status", "received_at"]
    )

    # RLS — tenant scoped for customer/txn; inbox readable by platform via app role
    # with no tenant predicate (ingest has no JWT tenant). FORCE + permissive insert.
    # Customers: strict tenant RLS.
    op.execute(sa.text("ALTER TABLE saas_customers ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE saas_customers FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            "CREATE POLICY saas_customers_tenant ON saas_customers "
            "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) "
            "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"
        )
    )
    op.execute(sa.text("GRANT SELECT, INSERT, UPDATE ON saas_customers TO hos_app"))

    # Transactions: allow SELECT when tenant context is unset so signed webhooks
    # can resolve provider_order_id → tenant, then set_config before writes.
    op.execute(sa.text("ALTER TABLE saas_payment_transactions ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE saas_payment_transactions FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            "CREATE POLICY saas_payment_transactions_tenant ON saas_payment_transactions "
            "USING ("
            "  tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
            "  OR NULLIF(current_setting('app.tenant_id', true), '') IS NULL"
            ") "
            "WITH CHECK ("
            "  tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
            ")"
        )
    )
    op.execute(
        sa.text("GRANT SELECT, INSERT, UPDATE ON saas_payment_transactions TO hos_app")
    )

    op.execute(sa.text("ALTER TABLE saas_webhook_inbox ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE saas_webhook_inbox FORCE ROW LEVEL SECURITY"))
    # Webhook ingest runs without tenant context; allow app role full DML.
    op.execute(
        sa.text(
            "CREATE POLICY saas_webhook_inbox_app ON saas_webhook_inbox "
            "USING (true) WITH CHECK (true)"
        )
    )
    op.execute(sa.text("GRANT SELECT, INSERT, UPDATE ON saas_webhook_inbox TO hos_app"))


def downgrade() -> None:
    op.execute(sa.text("DROP POLICY IF EXISTS saas_webhook_inbox_app ON saas_webhook_inbox"))
    op.execute(
        sa.text("DROP POLICY IF EXISTS saas_payment_transactions_tenant ON saas_payment_transactions")
    )
    op.execute(sa.text("DROP POLICY IF EXISTS saas_customers_tenant ON saas_customers"))
    op.drop_table("saas_webhook_inbox")
    op.drop_table("saas_payment_transactions")
    op.drop_table("saas_customers")
