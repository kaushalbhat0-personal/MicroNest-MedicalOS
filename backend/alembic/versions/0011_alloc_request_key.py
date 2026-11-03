"""0011 payment allocation request identity + single-reversal guard.

P4.5 needs two small additive guarantees on `payment_allocations`:

1. `idempotency_key` (nullable, no uniqueness): allocation commands are
   critical financial commands. The key is stored per allocation row and
   scoped by the payment advisory lock: replay with the same key and the
   same (invoice, amount) set returns the existing rows; the same key with
   a divergent set is a 409. Uniqueness is deliberately NOT enforced —
   one allocate call writes N rows sharing one key — the lock plus the
   exact-set compare is the deterministic guard.
2. One reversal per allocation: a partial unique index on
   `reversal_of_id` so a forward allocation row can be cancelled by at
   most one reversing row. Balances derive from forward rows minus
   reversed rows; the index keeps that derivation unambiguous.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_alloc_request_key"
down_revision: str | Sequence[str] | None = "0010_invoice_guard"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "payment_allocations",
        sa.Column("idempotency_key", sa.String(64), nullable=True),
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_alloc_reversal_once "
        "ON payment_allocations (reversal_of_id) "
        "WHERE reversal_of_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_alloc_reversal_once")
    op.drop_column("payment_allocations", "idempotency_key")
