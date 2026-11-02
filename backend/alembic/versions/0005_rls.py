"""0005 RLS defense-in-depth + least-privilege grants.

Application authorization is authoritative; RLS guarantees that a missing
tenant filter fails closed instead of leaking. Registry tables
(users/credentials/sessions/tenants/...) are intentionally NOT RLS'd —
they are guarded by service-level checks + isolation tests (documented in
docs/architecture/rls-model.md).

Also revokes UPDATE/DELETE on audit_events from the app role (append-only).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_rls"
down_revision: str | Sequence[str] | None = "0004_audit_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "hos_app"
SETTING = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
ACTOR = "NULLIF(current_setting('app.user_id', true), '')::uuid"

# (table, using, with_check, extra_grants)
RLS_TABLES = [
    ("locations", f"tenant_id = {SETTING}", f"tenant_id = {SETTING}"),
    ("memberships", f"tenant_id = {SETTING} OR user_id = {ACTOR}", f"tenant_id = {SETTING}"),
    (
        "membership_locations",
        f"EXISTS (SELECT 1 FROM memberships m WHERE m.id = membership_id AND m.tenant_id = {SETTING})",  # noqa: E501, S608
        f"EXISTS (SELECT 1 FROM memberships m WHERE m.id = membership_id AND m.tenant_id = {SETTING})",  # noqa: E501, S608
    ),
    ("roles", f"tenant_id IS NULL OR tenant_id = {SETTING}", f"tenant_id = {SETTING}"),
    (
        "practitioner_verifications",
        f"tenant_id = {SETTING}",
        f"tenant_id = {SETTING}",
    ),
    ("audit_events", f"tenant_id = {SETTING}", f"tenant_id = {SETTING}"),
]

NON_RLS_TABLES = [
    "users",
    "credentials",
    "sessions",
    "password_resets",
    "practitioners",
    "auth_events",
    "tenants",
    "outbox_events",
    # invitations: capability-gated, NOT tenant-gated. Reads happen only by
    # unguessable 256-bit token hash (single-use, expiring); there is no
    # endpoint that enumerates invitations. Writes on accept are tenant-scoped
    # by SETTING app.tenant_id to the invitation's own tenant (server-derived
    # from the token lookup, never client input) before the membership insert.
    "invitations",
]


def upgrade() -> None:
    op.execute(
        sa.text(
            f"DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') "
            f"THEN CREATE ROLE {APP_ROLE} NOLOGIN; END IF; END $$;"
        )
    )
    op.execute(sa.text(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}"))
    for table in [t for t, _, _ in RLS_TABLES] + NON_RLS_TABLES:
        op.execute(sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}"))
    op.execute(sa.text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO hos_app"))
    for table, using, check in RLS_TABLES:
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                f"CREATE POLICY {table}_tenant_isolation ON {table} "
                f"FOR ALL TO {APP_ROLE} USING ({using}) WITH CHECK ({check})"
            )
        )
    # Append-only audit: no UPDATE/DELETE policy exists, and the privilege
    # itself is revoked so even a policy change later cannot silently allow it.
    op.execute(sa.text(f"REVOKE UPDATE, DELETE ON audit_events FROM {APP_ROLE}"))


def downgrade() -> None:
    op.execute(sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON audit_events TO {APP_ROLE}"))
    for table, _, _ in RLS_TABLES:
        op.execute(sa.text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
        op.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))
