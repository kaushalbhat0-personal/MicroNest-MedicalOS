"""0023 P2.0 commercial plan catalog + subscription foundation.

Extends existing ``subscription_plans`` / ``subscriptions`` (no duplicate
tables). Adds:

- Plan catalog metadata + family/version for immutable revisions
- Subscription grace/cancel/provider_ref columns (provider unused)
- ``subscription_events`` append-only history (RLS tenant-isolated)
- Seed paid catalog rows (starter / growth) + backfill trial plan
- Seed permission growth: ``subscription.read`` / ``subscription.manage``

Billing separation unchanged: no clinic billing FKs. No payment provider.
Limits remain informational (enforcement is P2.2).
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023_subscription_foundation"
down_revision: str | Sequence[str] | None = "0022_staff"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "hos_app"
SETTING = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"

# Mirror SEED_ROLES growth for seed rows wiped/updated in place.
# Full bundles are recomputed in app code; migration only merges the new
# keys into existing seed JSON so upgraded DBs pick them up.
NEW_TENANT_ADMIN = ["subscription.read"]
NEW_PLATFORM_ADMIN = ["subscription.manage"]


def upgrade() -> None:
    # --- subscription_plans catalog enrichment ---
    op.add_column(
        "subscription_plans",
        sa.Column("family_code", sa.Text(), nullable=True),
    )
    op.add_column(
        "subscription_plans",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "subscription_plans",
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "subscription_plans",
        sa.Column("currency", sa.Text(), nullable=False, server_default="INR"),
    )
    op.add_column(
        "subscription_plans",
        sa.Column("billing_interval", sa.Text(), nullable=True),
    )
    op.add_column(
        "subscription_plans",
        sa.Column("price_minor", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "subscription_plans",
        sa.Column(
            "features",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.execute(sa.text("UPDATE subscription_plans SET family_code = code WHERE family_code IS NULL"))
    op.alter_column("subscription_plans", "family_code", nullable=False)
    op.create_unique_constraint(
        "uq_subscription_plans_family_version",
        "subscription_plans",
        ["family_code", "version"],
    )
    op.create_index("ix_subscription_plans_family", "subscription_plans", ["family_code"])
    op.create_check_constraint(
        "ck_plan_billing_interval",
        "subscription_plans",
        "billing_interval IS NULL OR billing_interval IN ('month', 'year')",
    )
    op.create_check_constraint(
        "ck_plan_currency",
        "subscription_plans",
        "currency = 'INR'",
    )
    op.create_check_constraint(
        "ck_plan_price_minor",
        "subscription_plans",
        "price_minor >= 0",
    )
    op.create_check_constraint(
        "ck_plan_version_positive",
        "subscription_plans",
        "version >= 1",
    )

    conn = op.get_bind()
    feat_trial = json.dumps(
        {
            "operations_dashboard": True,
            "patient_portal": True,
            "clinic_billing": True,
            "informational_limits": True,
        }
    )
    feat_starter = feat_trial
    feat_growth = json.dumps(
        {
            "operations_dashboard": True,
            "patient_portal": True,
            "clinic_billing": True,
            "inventory": True,
            "staff_workforce": True,
            "informational_limits": True,
        }
    )

    # Backfill trial row metadata (deterministic; preserves id/code).
    conn.execute(
        sa.text(
            "UPDATE subscription_plans SET "
            " description = '14-day trial for new clinic workspaces. "
            "Limits are informational only until entitlement enforcement.', "
            " currency = 'INR', billing_interval = NULL, price_minor = 0, "
            " features = CAST(:feat AS JSONB), "
            " family_code = 'trial-14d', version = 1, "
            " updated_at = now() "
            "WHERE code = 'trial-14d'"
        ),
        {"feat": feat_trial},
    )

    # Paid catalog (active for display; not auto-assigned; no checkout).
    conn.execute(
        sa.text(
            "INSERT INTO subscription_plans "
            "(id, code, name, family_code, version, description, currency, "
            " billing_interval, price_minor, features, "
            " max_locations, max_practitioners, max_staff_seats, trial_days, "
            " is_active, created_at, updated_at) "
            "VALUES "
            "(gen_random_uuid(), 'starter-v1', 'Starter', 'starter', 1, "
            " 'Single-location clinic starter plan. Price is catalog-only; "
            "no payment provider is connected.', 'INR', 'month', 499900, "
            " CAST(:feat_s AS JSONB), 1, 5, 15, 0, true, now(), now()), "
            "(gen_random_uuid(), 'growth-v1', 'Growth', 'growth', 1, "
            " 'Multi-location growth plan. Price is catalog-only; "
            "no payment provider is connected.', 'INR', 'month', 999900, "
            " CAST(:feat_g AS JSONB), 5, 25, 50, 0, true, now(), now()) "
            "ON CONFLICT (code) DO NOTHING"
        ),
        {"feat_s": feat_starter, "feat_g": feat_growth},
    )

    # --- subscriptions enrichment ---
    op.add_column(
        "subscriptions",
        sa.Column("grace_ends_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "subscriptions",
        sa.Column("cancelled_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "subscriptions",
        sa.Column("cancel_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "subscriptions",
        sa.Column("provider_ref", sa.Text(), nullable=True),
    )
    # provider_ref reserved for future payment customer/subscription ids.
    # Never populated in P2.0.

    # --- subscription_events (history) ---
    op.create_table(
        "subscription_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("from_status", sa.Text(), nullable=True),
        sa.Column("to_status", sa.Text(), nullable=True),
        sa.Column("from_plan_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("to_plan_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["subscriptions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["from_plan_id"], ["subscription_plans.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["to_plan_id"], ["subscription_plans.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "event_type IN ('created','status_transition','plan_assigned','trial_extended')",
            name="ck_sub_event_type",
        ),
    )
    op.create_index(
        "ix_subscription_events_tenant_created",
        "subscription_events",
        ["tenant_id", "created_at"],
    )
    op.execute(sa.text(f"GRANT SELECT, INSERT ON subscription_events TO {APP_ROLE}"))
    # No UPDATE/DELETE for app role — append-only history.
    op.execute(sa.text("ALTER TABLE subscription_events ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE subscription_events FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            "CREATE POLICY subscription_events_tenant_isolation ON subscription_events "
            f"FOR ALL TO {APP_ROLE} "
            f"USING (tenant_id = {SETTING}) WITH CHECK (tenant_id = {SETTING})"
        )
    )
    # Platform read (same pattern as 0017 subscriptions_platform_read).
    platform_using = (
        "EXISTS (SELECT 1 FROM users WHERE users.id = "
        "NULLIF(current_setting('app.user_id', true), '')::uuid "
        "AND users.is_platform_admin AND users.is_active)"
    )
    op.execute(
        sa.text(
            "CREATE POLICY subscription_events_platform_read ON subscription_events "
            f"FOR SELECT TO {APP_ROLE} USING ({platform_using})"
        )
    )

    # Backfill created events for existing subscriptions (deterministic).
    op.execute(
        sa.text(
            "INSERT INTO subscription_events "
            "(id, tenant_id, subscription_id, event_type, from_status, to_status, "
            " from_plan_id, to_plan_id, actor_id, note, created_at) "
            "SELECT gen_random_uuid(), s.tenant_id, s.id, 'created', NULL, s.status, "
            " NULL, s.plan_id, NULL, 'backfill from 0023_subscription_foundation', "
            " s.created_at "
            "FROM subscriptions s "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM subscription_events e WHERE e.subscription_id = s.id"
            ")"
        )
    )

    # Seed permission growth (merge into seed roles only).
    for role_name, extra in (
        ("tenant_admin", NEW_TENANT_ADMIN),
        ("platform_admin", NEW_PLATFORM_ADMIN),
    ):
        row = conn.execute(
            sa.text(
                "SELECT id, permissions FROM roles "
                "WHERE is_seed AND tenant_id IS NULL AND name = :n"
            ),
            {"n": role_name},
        ).mappings().first()
        if row is None:
            continue
        perms = list(row["permissions"] or [])
        for p in extra:
            if p not in perms:
                perms.append(p)
        conn.execute(
            sa.text(
                "UPDATE roles SET permissions = CAST(:perms AS JSONB) WHERE id = :id"
            ),
            {"perms": json.dumps(sorted(perms)), "id": row["id"]},
        )


def downgrade() -> None:
    op.execute(sa.text("DROP POLICY IF EXISTS subscription_events_platform_read ON subscription_events"))
    op.execute(
        sa.text("DROP POLICY IF EXISTS subscription_events_tenant_isolation ON subscription_events")
    )
    op.drop_table("subscription_events")
    op.drop_column("subscriptions", "provider_ref")
    op.drop_column("subscriptions", "cancel_reason")
    op.drop_column("subscriptions", "cancelled_at")
    op.drop_column("subscriptions", "grace_ends_at")
    op.drop_constraint("ck_plan_version_positive", "subscription_plans", type_="check")
    op.drop_constraint("ck_plan_price_minor", "subscription_plans", type_="check")
    op.drop_constraint("ck_plan_currency", "subscription_plans", type_="check")
    op.drop_constraint("ck_plan_billing_interval", "subscription_plans", type_="check")
    op.drop_index("ix_subscription_plans_family", table_name="subscription_plans")
    op.drop_constraint(
        "uq_subscription_plans_family_version", "subscription_plans", type_="unique"
    )
    op.drop_column("subscription_plans", "features")
    op.drop_column("subscription_plans", "price_minor")
    op.drop_column("subscription_plans", "billing_interval")
    op.drop_column("subscription_plans", "currency")
    op.drop_column("subscription_plans", "description")
    op.drop_column("subscription_plans", "version")
    op.drop_column("subscription_plans", "family_code")
    # Seeded starter/growth rows remain until manually removed; safe.
    # Permission keys left in seed roles (harmless if unused).
