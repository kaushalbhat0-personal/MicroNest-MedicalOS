"""0016 workspace provisioning foundation: ownership, trial, specialties.

O1.2a release train (atomic `POST /api/v1/workspaces`):

- `tenant_owners`: commercial authority ("who purchased/is responsible").
  Explicit association table per the approved ownership model — never a
  scalar `owner_user_id`. Ownership grants no authorization; every request
  still requires a membership + permission + tenant match + RLS.
- `subscription_plans` (non-RLS catalog, readable like seed roles; rows are
  versioned by migration, never edited in place) + seed `trial-14d`, and
  `subscriptions` (one row per tenant, RLS tenant-isolated). Trial only:
  14 days, no card, no charge, no enforcement interlocks in O1.
- `tenant_specialties`: relational enablement set (one row per pack).
  Locations inherit the tenant set by convention — no `location_specialties`
  table in O1.2a (deferred until a real operational requirement exists).
- `workspace_provisions`: durable per-user idempotency ledger for workspace
  creation. UNIQUE(user_id, idempotency_key); same key + same request hash
  replays, same key + different hash is a 409. Written in the SAME
  transaction as the provisioned rows (transactionally consistent; a
  rollback leaves zero rows anywhere).

Billing separation (hard invariant): no subscription FK in clinic/billing
tables, no patient/clinical FK in subscription tables; the ledgers join by
tenant_id only.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0016_workspace_provisioning"
down_revision: str | Sequence[str] | None = "0015_signup_verification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "hos_app"
SETTING = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
ACTOR = "NULLIF(current_setting('app.user_id', true), '')::uuid"

# Keep in sync with app/modules/workspaces/registry.py SPECIALTIES keys.
SPECIALTY_CODES = ("dental", "ophthalmology")

RLS_TABLES = [
    ("tenant_owners", f"tenant_id = {SETTING}", f"tenant_id = {SETTING}"),
    ("subscriptions", f"tenant_id = {SETTING}", f"tenant_id = {SETTING}"),
    ("tenant_specialties", f"tenant_id = {SETTING}", f"tenant_id = {SETTING}"),
    # User-scoped ledger (no tenant exists yet at claim time): the caller
    # only ever sees their own rows, mirroring the memberships bootstrap
    # exception. Writes stay user-pinned via WITH CHECK.
    ("workspace_provisions", f"user_id = {ACTOR}", f"user_id = {ACTOR}"),
]


def upgrade() -> None:
    op.create_table(
        "subscription_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("max_locations", sa.Integer(), nullable=False),
        sa.Column("max_practitioners", sa.Integer(), nullable=False),
        sa.Column("max_staff_seats", sa.Integer(), nullable=False),
        sa.Column("trial_days", sa.Integer(), nullable=False, server_default="14"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="trial"),
        sa.Column("trial_ends_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("period_start", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("period_end", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN " "('trial','active','past_due','grace','suspended','cancelled','expired')",
            name="ck_sub_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["subscription_plans.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_subscriptions_tenant"),
    )
    op.create_table(
        "tenant_owners",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_tenant_owner"),
    )
    op.create_index("ix_tenant_owners_tenant", "tenant_owners", ["tenant_id"])
    op.create_index("ix_tenant_owners_user", "tenant_owners", ["user_id"])
    op.create_table(
        "tenant_specialties",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("specialty_code", sa.Text(), nullable=False),
        sa.Column("pack_version", sa.Text(), nullable=False),
        sa.Column("enabled_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("enabled_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint(
            "specialty_code IN ('dental', 'ophthalmology')",
            name="ck_tenant_specialty_code",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["enabled_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("tenant_id", "specialty_code"),
    )
    op.create_table(
        "workspace_provisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.CHAR(64), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("result_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'failed')",
            name="ck_workspace_provision_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_workspace_provision_user_key"),
    )

    # Seed the trial catalog row exactly once (UNIQUE(code) guards re-runs).
    op.execute(
        sa.text(
            "INSERT INTO subscription_plans "
            "(id, code, name, max_locations, max_practitioners, max_staff_seats, "
            " trial_days, is_active, created_at, updated_at) "
            "VALUES (gen_random_uuid(), 'trial-14d', 'Trial (14-day)', "
            " 3, 10, 25, 14, true, now(), now())"
        )
    )

    for table in ["subscription_plans"] + [t for t, _, _ in RLS_TABLES]:
        op.execute(sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}"))
    op.execute(sa.text(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}"))
    for table, using, check in RLS_TABLES:
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                f"CREATE POLICY {table}_tenant_isolation ON {table} "
                f"FOR ALL TO {APP_ROLE} USING ({using}) WITH CHECK ({check})"
            )
        )


def downgrade() -> None:
    for table, _, _ in RLS_TABLES:
        op.execute(sa.text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
        op.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))
    op.drop_table("workspace_provisions")
    op.drop_table("tenant_specialties")
    op.drop_index("ix_tenant_owners_user", table_name="tenant_owners")
    op.drop_index("ix_tenant_owners_tenant", table_name="tenant_owners")
    op.drop_table("tenant_owners")
    op.drop_table("subscriptions")
    op.drop_table("subscription_plans")
