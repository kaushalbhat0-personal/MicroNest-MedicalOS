"""0025 P2.3 trial plan includes all enforced features for evaluation.

Starter remains the limited paid SKU (no inventory / staff_workforce).
Growth remains the full SKU. Trial enables feature evaluation during signup.
No schema change.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_commercial_gates"
down_revision: str | Sequence[str] | None = "0024_entitlement_shadow"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TRIAL_FEATURES = {
    "patient_portal": True,
    "inventory": True,
    "operations_dashboard": True,
    "clinic_billing": True,
    "staff_workforce": True,
    "informational_limits": True,
}


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE subscription_plans SET features = CAST(:feat AS JSONB), "
            " updated_at = now() WHERE code = 'trial-14d'"
        ),
        {"feat": json.dumps(TRIAL_FEATURES)},
    )


def downgrade() -> None:
    # Restore pre-P2.3 trial feature map (inventory/staff off).
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE subscription_plans SET features = CAST(:feat AS JSONB), "
            " updated_at = now() WHERE code = 'trial-14d'"
        ),
        {
            "feat": json.dumps(
                {
                    "patient_portal": True,
                    "inventory": False,
                    "operations_dashboard": True,
                    "clinic_billing": True,
                    "staff_workforce": False,
                    "informational_limits": True,
                }
            )
        },
    )
