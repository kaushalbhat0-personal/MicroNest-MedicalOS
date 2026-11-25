"""0028 Native session metadata for desktop clients.

Adds optional client_platform, device_label, and client_instance_id to
sessions. Nullable for backward compatibility with existing web sessions.
No change to refresh_hash or JWT semantics.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028_native_session_metadata"
down_revision: str | Sequence[str] | None = "0027_saas_payment_reliability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("client_platform", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "sessions",
        sa.Column("device_label", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "sessions",
        sa.Column("client_instance_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_sessions_client_platform",
        "sessions",
        ["client_platform"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_sessions_client_platform", table_name="sessions")
    op.drop_column("sessions", "client_instance_id")
    op.drop_column("sessions", "device_label")
    op.drop_column("sessions", "client_platform")
