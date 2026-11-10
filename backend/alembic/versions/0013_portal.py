"""0013 patient portal foundation: portal_links + patient role portal perms.

New table `portal_links` binds a portal identity (users row with a
`patient`-role membership) to exactly one patient per tenant. Portal
authorization resolves ownership server-side from this table; the browser
never supplies patient_id as proof of ownership.

No portal session table: portal users authenticate through the existing
users/sessions/cookies/JWT machinery. Revocation reuses session revocation
plus link revocation (fail-closed on both).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0013_portal"
down_revision: str | Sequence[str] | None = "0012_credit_draft"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "hos_app"
SETTING = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"

# Must match platform/authz/permissions.py SEED_ROLES["patient"].
PATIENT_PORTAL_PERMS = ["portal.appointment.cancel", "portal.read"]
# Frozen P4.8 bundle (downgrade path only).
PATIENT_EMPTY: list[str] = []


def upgrade() -> None:
    import json as _json

    op.create_table(
        "portal_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["patient_id"], ["patients.id"], ondelete="RESTRICT", name="fk_portal_patient"
        ),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_portal_link_tenant_user"),
        sa.CheckConstraint("status IN ('active','revoked')", name="ck_portal_link_status"),
    )
    op.create_index("ix_portal_links_tenant", "portal_links", ["tenant_id"])
    op.create_index("ix_portal_links_patient", "portal_links", ["patient_id"])

    op.execute(sa.text("GRANT SELECT, INSERT, UPDATE, DELETE ON portal_links TO hos_app"))
    op.execute(sa.text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO hos_app"))
    op.execute(sa.text("ALTER TABLE portal_links ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE portal_links FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            "CREATE POLICY portal_links_tenant_isolation ON portal_links "
            f"FOR ALL TO {APP_ROLE} USING (tenant_id = {SETTING}) "
            f"WITH CHECK (tenant_id = {SETTING})"
        )
    )

    # Existing installs: grant the portal allow-list to the patient seed role.
    op.execute(
        sa.text(
            "UPDATE roles SET permissions = CAST(:perms AS JSONB) "
            "WHERE tenant_id IS NULL AND name = 'patient'"
        ).bindparams(perms=_json.dumps(sorted(PATIENT_PORTAL_PERMS)))
    )


def downgrade() -> None:
    import json as _json

    op.execute(
        sa.text(
            "UPDATE roles SET permissions = CAST(:perms AS JSONB) "
            "WHERE tenant_id IS NULL AND name = 'patient'"
        ).bindparams(perms=_json.dumps(sorted(PATIENT_EMPTY)))
    )
    op.execute(sa.text("DROP POLICY IF EXISTS portal_links_tenant_isolation ON portal_links"))
    op.execute(sa.text("ALTER TABLE portal_links DISABLE ROW LEVEL SECURITY"))
    op.drop_index("ix_portal_links_patient", table_name="portal_links")
    op.drop_index("ix_portal_links_tenant", table_name="portal_links")
    op.drop_table("portal_links")
