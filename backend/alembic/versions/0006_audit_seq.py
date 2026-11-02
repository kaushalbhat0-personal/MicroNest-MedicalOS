"""0006 audit sequence key.

Revision ID: 0006_audit_seq
Revises: 0005_rls

Strictly monotonic insertion order for the hash chain. UUIDv7 ids carry
random bits (not monotonic within a timestamp) and occurred_at can tie
under coarse clocks — ordering by (occurred_at, id) linked the chain
nondeterministically. seq (identity) is the order key from here on.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_audit_seq"
down_revision: str | Sequence[str] | None = "0005_rls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text("ALTER TABLE audit_events " "ADD COLUMN seq BIGINT GENERATED ALWAYS AS IDENTITY")
    )
    op.create_index("ix_audit_tenant_day_seq", "audit_events", ["tenant_id", "chain_day", "seq"])


def downgrade() -> None:
    op.drop_index("ix_audit_tenant_day_seq", table_name="audit_events")
    op.drop_column("audit_events", "seq")
