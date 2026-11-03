"""0010 invoice conversion guard: one estimate line converts at most once.

Schema defect found during P4.4 (invoice foundation):

- `invoice_lines.source_estimate_line_id` carried a foreign key but no
  uniqueness, so the same estimate line could be snapshotted into N
  invoices — silent duplicate financial truth. The estimate header alone
  (`issued` vs `converted`) distinguishes *fully* converted estimates but
  cannot prevent a second conversion of an already-converted line.

Smallest correction: a partial unique index enforcing at-most-once
conversion per estimate line. Partial vs full conversion continues to be
derived, not stored: `converted` = every estimate line has an invoice
line; still-`issued` with some converted lines = partial conversion. No
new tables, no new columns, no lifecycle changes.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010_invoice_guard"
down_revision: str | Sequence[str] | None = "0009_billing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_invoice_lines_source_line_once "
        "ON invoice_lines (source_estimate_line_id) "
        "WHERE source_estimate_line_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_invoice_lines_source_line_once")
