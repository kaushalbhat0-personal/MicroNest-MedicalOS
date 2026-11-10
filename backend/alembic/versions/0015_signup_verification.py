"""0015 signup verification: users.email_verified_at + email_verifications.

Public signup (O1.1) issues a single-use expiring challenge per user. The
table is Non-RLS and capability-gated like password_resets/invitations:
rows are reachable only by unguessable 256-bit token hash (single-use,
expiring); there is no endpoint that enumerates challenges. Raw tokens are
never persisted — only SHA-256 digests.

Existing users are backfilled verified: every pre-O1.1 user entered via a
trusted path (operator bootstrap, staff invite accept, staff-gated portal
enrollment). New public signups start unverified (NULL).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0015_signup_verification"
down_revision: str | Sequence[str] | None = "0014_portal_selfread"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    # Trusted-path backfill: operator/invite/portal users predate challenges.
    op.execute(sa.text("UPDATE users SET email_verified_at = created_at"))

    op.create_table(
        "email_verifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("superseded_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_email_verifications_user", "email_verifications", ["user_id"])
    # At most one live (unused, non-superseded) challenge per user. Expired
    # rows stay covered until a resend supersedes them (lazy cleanup).
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX uq_email_verifications_pending_user "
            "ON email_verifications (user_id) "
            "WHERE used_at IS NULL AND superseded_at IS NULL"
        )
    )
    op.execute(sa.text("GRANT SELECT, INSERT, UPDATE, DELETE ON email_verifications TO hos_app"))
    op.execute(sa.text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO hos_app"))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS uq_email_verifications_pending_user"))
    op.drop_index("ix_email_verifications_user", table_name="email_verifications")
    op.drop_table("email_verifications")
    op.drop_column("users", "email_verified_at")
