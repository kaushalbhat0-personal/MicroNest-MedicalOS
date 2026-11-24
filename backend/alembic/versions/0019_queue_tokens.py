"""0019 reception queue tokens on appointments.

Additive columns only:
- queue_token: opaque per-location daily sequence (no PHI)
- queue_date: local service date used for uniqueness

Tokens are assigned server-side on check-in / walk-in. Cancel, no-show,
and completion keep the token for audit. Reschedule before check-in never
had a token; checked-in appointments cannot be rescheduled.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_queue_tokens"
down_revision: str | Sequence[str] | None = "0018_patient_crm_availability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("appointments", sa.Column("queue_token", sa.Integer(), nullable=True))
    op.add_column("appointments", sa.Column("queue_date", sa.Date(), nullable=True))
    op.create_index(
        "uq_appointments_location_queue_day_token",
        "appointments",
        ["location_id", "queue_date", "queue_token"],
        unique=True,
        postgresql_where=sa.text("queue_token IS NOT NULL"),
    )
    op.create_index(
        "ix_appointments_location_queue_date",
        "appointments",
        ["location_id", "queue_date"],
        postgresql_where=sa.text("queue_date IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_appointments_location_queue_date", table_name="appointments")
    op.drop_index("uq_appointments_location_queue_day_token", table_name="appointments")
    op.drop_column("appointments", "queue_date")
    op.drop_column("appointments", "queue_token")
