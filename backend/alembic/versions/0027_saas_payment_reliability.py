"""0027 P2.5 durable webhook inbox + refund amount tracking.

Extends saas_webhook_inbox lifecycle and saas_payment_transactions for
partial refunds. Adds cancel_at_period_end on subscriptions.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027_saas_payment_reliability"
down_revision: str | Sequence[str] | None = "0026_saas_payments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "saas_webhook_inbox",
        sa.Column("next_attempt_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "saas_webhook_inbox",
        sa.Column("locked_until", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "saas_webhook_inbox",
        sa.Column(
            "event_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.execute(sa.text("ALTER TABLE saas_webhook_inbox DROP CONSTRAINT IF EXISTS ck_saas_webhook_status"))
    op.execute(
        sa.text(
            "ALTER TABLE saas_webhook_inbox ADD CONSTRAINT ck_saas_webhook_status "
            "CHECK (status IN ("
            "'received','verified','pending','processing','processed',"
            "'retryable_failure','permanent_failure','ignored','duplicate'"
            "))"
        )
    )
    op.create_index(
        "ix_saas_webhook_retry",
        "saas_webhook_inbox",
        ["status", "next_attempt_at"],
    )

    op.add_column(
        "saas_payment_transactions",
        sa.Column(
            "refunded_amount_minor",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.execute(
        sa.text("ALTER TABLE saas_payment_transactions DROP CONSTRAINT IF EXISTS ck_saas_txn_status")
    )
    op.execute(
        sa.text(
            "ALTER TABLE saas_payment_transactions ADD CONSTRAINT ck_saas_txn_status "
            "CHECK (status IN ("
            "'pending','paid','failed','partially_refunded','refunded',"
            "'cancelled','disputed'"
            "))"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE saas_payment_transactions "
            "ADD CONSTRAINT ck_saas_txn_refunded_amount "
            "CHECK (refunded_amount_minor >= 0 AND refunded_amount_minor <= amount_minor)"
        )
    )

    op.add_column(
        "subscriptions",
        sa.Column(
            "cancel_at_period_end",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("subscriptions", "cancel_at_period_end")
    op.execute(
        sa.text(
            "ALTER TABLE saas_payment_transactions "
            "DROP CONSTRAINT IF EXISTS ck_saas_txn_refunded_amount"
        )
    )
    op.execute(
        sa.text("ALTER TABLE saas_payment_transactions DROP CONSTRAINT IF EXISTS ck_saas_txn_status")
    )
    op.execute(
        sa.text(
            "ALTER TABLE saas_payment_transactions ADD CONSTRAINT ck_saas_txn_status "
            "CHECK (status IN ('pending','paid','failed','refunded','cancelled'))"
        )
    )
    op.drop_column("saas_payment_transactions", "refunded_amount_minor")
    op.drop_index("ix_saas_webhook_retry", table_name="saas_webhook_inbox")
    op.execute(sa.text("ALTER TABLE saas_webhook_inbox DROP CONSTRAINT IF EXISTS ck_saas_webhook_status"))
    op.execute(
        sa.text(
            "ALTER TABLE saas_webhook_inbox ADD CONSTRAINT ck_saas_webhook_status "
            "CHECK (status IN ('received','processed','failed','ignored','duplicate'))"
        )
    )
    op.drop_column("saas_webhook_inbox", "event_refs")
    op.drop_column("saas_webhook_inbox", "locked_until")
    op.drop_column("saas_webhook_inbox", "next_attempt_at")
