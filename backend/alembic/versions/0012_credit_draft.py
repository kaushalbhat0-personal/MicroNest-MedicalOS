"""0012 credit-note draft state (P4.6).

P4.6 implements the task-minimum credit-note lifecycle DRAFT → ISSUED
with void-from-draft only. The P4.1 model enum carried only
{issued, voided}, so this migration adds the 'draft' label and moves the
column default to 'draft' (drafts carry no number, mirroring invoices).
No issued-void semantics are introduced: an issued note is applied via
balance derivation immediately, so "void only before application"
(P4-01 §15) means void-from-draft. Downgrade is a documented no-op for
the label (the 0009 downgrade drops the enum type wholesale).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012_credit_draft"
down_revision: str | Sequence[str] | None = "0011_alloc_request_key"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NOTE: the pre-existing server default ('issued') is left untouched:
    # SET DEFAULT to the new label in the same transaction is rejected by
    # PostgreSQL ("unsafe use of new value … must be committed first"), and
    # the default is irrelevant — every service path sets status explicitly
    # and the SQLAlchemy model default is client-side.
    op.execute("ALTER TYPE credit_note_status ADD VALUE IF NOT EXISTS 'draft'")


def downgrade() -> None:
    # No-op: enum labels cannot be removed while the type exists; the 0009
    # downgrade drops the type wholesale.
    pass
