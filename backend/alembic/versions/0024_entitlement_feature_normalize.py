"""0024 P2.1 normalize plan.features for shadow entitlement evaluation.

Additive data-only: sets a consistent boolean feature map on known catalog
rows. No schema change. No enforcement. Downgrade is a no-op for JSON shape.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_entitlement_shadow"
down_revision: str | Sequence[str] | None = "0023_subscription_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Starter remains the limited paid SKU. Trial features are finalized in 0025.
TRIAL_STARTER = {
    "patient_portal": True,
    "inventory": False,
    "operations_dashboard": True,
    "clinic_billing": True,
    "staff_workforce": False,
    "informational_limits": True,
}
GROWTH = {
    "patient_portal": True,
    "inventory": True,
    "operations_dashboard": True,
    "clinic_billing": True,
    "staff_workforce": True,
    "informational_limits": True,
}


def upgrade() -> None:
    conn = op.get_bind()
    for code, feat in (
        ("trial-14d", TRIAL_STARTER),
        ("starter-v1", TRIAL_STARTER),
        ("growth-v1", GROWTH),
    ):
        conn.execute(
            sa.text(
                "UPDATE subscription_plans SET features = CAST(:feat AS JSONB), "
                " updated_at = now() WHERE code = :code"
            ),
            {"feat": json.dumps(feat), "code": code},
        )


def downgrade() -> None:
    # Feature maps remain valid informational JSON; no destructive revert.
    pass
