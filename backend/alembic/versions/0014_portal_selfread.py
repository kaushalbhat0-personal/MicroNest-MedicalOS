"""0014 portal link self-read: allow user_id = app.user_id in RLS USING.

portal_links pins ownership per (tenant, user). The workspaces routing
signal and any future self-service read must find a user's links without a
tenant selected yet — the same bootstrap exception memberships carry
(`tenant_id = SETTING OR user_id = ACTOR`). Writes stay tenant-pinned:
WITH CHECK still requires tenant_id = SETTING, so a caller can never
create or move a link outside the resolved tenant.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014_portal_selfread"
down_revision: str | Sequence[str] | None = "0013_portal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "hos_app"
SETTING = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
ACTOR = "NULLIF(current_setting('app.user_id', true), '')::uuid"


def upgrade() -> None:
    op.execute(sa.text("DROP POLICY IF EXISTS portal_links_tenant_isolation ON portal_links"))
    op.execute(
        sa.text(
            "CREATE POLICY portal_links_tenant_isolation ON portal_links "
            f"FOR ALL TO {APP_ROLE} USING (tenant_id = {SETTING} OR user_id = {ACTOR}) "
            f"WITH CHECK (tenant_id = {SETTING})"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP POLICY IF EXISTS portal_links_tenant_isolation ON portal_links"))
    op.execute(
        sa.text(
            "CREATE POLICY portal_links_tenant_isolation ON portal_links "
            f"FOR ALL TO {APP_ROLE} USING (tenant_id = {SETTING}) "
            f"WITH CHECK (tenant_id = {SETTING})"
        )
    )
