"""0017 O1.3R subscription/specialty read-only visibility.

Additive only — no table, column, or enforcement change:

- Idempotent re-seed of the `trial-14d` catalog row (`ON CONFLICT DO
  NOTHING`), so duplicate migration execution or repeated seed execution
  cannot create duplicate trial plans. The UNIQUE(code) constraint from
  0016 remains the primary duplicate guard.
- Platform-admin SELECT-only RLS policies on `subscriptions` and
  `tenant_specialties`. Tenant isolation is unchanged: the existing
  tenant-pinned FOR ALL policies stay in place (permissive policies are
  OR'd for reads). The new policies are FOR SELECT only, so the platform
  path cannot write subscription/specialty rows even if an endpoint bug
  tried to — reads stay read-only at the database layer. Clinical,
  billing, portal, membership, and location tables are untouched: the
  platform still has no clinical path.

Billing separation is unchanged: no FK is added anywhere in this
migration.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017_o13r_visibility"
down_revision: str | Sequence[str] | None = "0016_workspace_provisioning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "hos_app"

# Platform scope is the existing `is_platform_admin` user flag only (the
# same flag `get_platform_admin` checks). Active platform admins may read
# commercial metadata; deactivated admins and ordinary tenant users match
# nothing here. `users` is a non-RLS registry table the app role can read.
PLATFORM_ADMIN_USING = (
    "EXISTS (SELECT 1 FROM users WHERE users.id = "
    "NULLIF(current_setting('app.user_id', true), '')::uuid "
    "AND users.is_platform_admin AND users.is_active)"
)


def upgrade() -> None:
    # Re-seed guard: exactly one `trial-14d` row survives re-execution.
    # Values mirror 0016 exactly (trial-only, unenforced placeholders).
    op.execute(
        sa.text(
            "INSERT INTO subscription_plans "
            "(id, code, name, max_locations, max_practitioners, max_staff_seats, "
            " trial_days, is_active, created_at, updated_at) "
            "VALUES (gen_random_uuid(), 'trial-14d', 'Trial (14-day)', "
            " 3, 10, 25, 14, true, now(), now()) "
            "ON CONFLICT (code) DO NOTHING"
        )
    )
    # Platform read-only visibility (SELECT only; tenant writes unaffected).
    op.execute(
        sa.text(
            "CREATE POLICY subscriptions_platform_read ON subscriptions "
            f"FOR SELECT TO {APP_ROLE} USING ({PLATFORM_ADMIN_USING})"
        )
    )
    op.execute(
        sa.text(
            "CREATE POLICY tenant_specialties_platform_read ON tenant_specialties "
            f"FOR SELECT TO {APP_ROLE} USING ({PLATFORM_ADMIN_USING})"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DROP POLICY IF EXISTS tenant_specialties_platform_read "
            "ON tenant_specialties"
        )
    )
    op.execute(sa.text("DROP POLICY IF EXISTS subscriptions_platform_read ON subscriptions"))
    # The idempotent seed insert is data, not schema: a downgrade leaves the
    # single `trial-14d` row in place (0016's downgrade drops the table).
