"""0018 patient CRM fields + location working hours + seed permission growth.

- Additive columns on `patients` (email, DOB, emergency contact).
- New `location_working_hours` (tenant-scoped, RLS).
- Seed role updates: `patient.update` for tenant_admin/receptionist;
  `portal.appointment.book` for patient portal role.

Downgrade drops the new table/columns and restores prior seed bundles.
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0018_patient_crm_availability"
down_revision: str | Sequence[str] | None = "0017_o13r_visibility"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "hos_app"
SETTING = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"

CLINICAL_ADMIN = [
    "encounter.open",
    "encounter.close",
    "encounter.read",
    "clinical.read",
    "clinical.create",
    "prescription.read",
    "prescription.create",
    "prescription.sign",
    "dental.read",
    "dental.record",
    "plan.manage",
]
BILLING_FULL = [
    "billing.read",
    "billing.create",
    "invoice.issue",
    "payment.record",
    "billing.refund",
    "billing.config",
]
BASE_TENANT_ADMIN = [
    "tenant.read",
    "settings.manage",
    "staff.invite",
    "staff.manage",
    "roles.manage",
    "locations.manage",
    "audit.read",
    "appointment.read",
    "appointment.create",
    "appointment.update",
    "patient.read",
    "patient.create",
    "patient.update",
]
ROLE_PERMS = {
    "tenant_admin": BASE_TENANT_ADMIN + CLINICAL_ADMIN + BILLING_FULL,
    "doctor": ["tenant.read", "appointment.read", "appointment.update", "patient.read"]
    + CLINICAL_ADMIN
    + ["billing.read", "billing.create"],
    "receptionist": [
        "tenant.read",
        "appointment.read",
        "appointment.create",
        "appointment.update",
        "patient.read",
        "patient.create",
        "patient.update",
        "encounter.open",
        "encounter.read",
        "billing.read",
        "payment.record",
    ],
    "nurse": [
        "tenant.read",
        "appointment.read",
        "patient.read",
        "encounter.read",
        "clinical.read",
        "clinical.create",
    ],
    "accountant": ["tenant.read"] + BILLING_FULL,
    "staff": ["tenant.read"],
    "patient": [
        "portal.read",
        "portal.appointment.cancel",
        "portal.appointment.book",
    ],
    "platform_admin": [
        "platform.tenant.create",
        "platform.tenant.suspend",
        "platform.health",
    ],
}

# Frozen 0017-era bundles for downgrade (must match catalog before this revision).
PRIOR_BASE_TENANT_ADMIN = [
    "tenant.read",
    "settings.manage",
    "staff.invite",
    "staff.manage",
    "roles.manage",
    "locations.manage",
    "audit.read",
    "appointment.read",
    "appointment.create",
    "appointment.update",
    "patient.read",
    "patient.create",
]
PRIOR_ROLE_PERMS = {
    "tenant_admin": PRIOR_BASE_TENANT_ADMIN + CLINICAL_ADMIN + BILLING_FULL,
    "doctor": ["tenant.read", "appointment.read", "appointment.update", "patient.read"]
    + CLINICAL_ADMIN
    + ["billing.read", "billing.create"],
    "receptionist": [
        "tenant.read",
        "appointment.read",
        "appointment.create",
        "appointment.update",
        "patient.read",
        "patient.create",
        "encounter.open",
        "encounter.read",
        "billing.read",
        "payment.record",
    ],
    "nurse": [
        "tenant.read",
        "appointment.read",
        "patient.read",
        "encounter.read",
        "clinical.read",
        "clinical.create",
    ],
    "accountant": ["tenant.read"] + BILLING_FULL,
    "staff": ["tenant.read"],
    "patient": ["portal.read", "portal.appointment.cancel"],
    "platform_admin": [
        "platform.tenant.create",
        "platform.tenant.suspend",
        "platform.health",
    ],
}


def upgrade() -> None:
    op.add_column("patients", sa.Column("email", sa.String(length=320), nullable=True))
    op.add_column("patients", sa.Column("date_of_birth", sa.Date(), nullable=True))
    op.add_column(
        "patients", sa.Column("emergency_contact_name", sa.String(length=200), nullable=True)
    )
    op.add_column(
        "patients", sa.Column("emergency_contact_phone", sa.String(length=32), nullable=True)
    )
    op.create_index("ix_patients_tenant_phone", "patients", ["tenant_id", "phone"])
    op.create_index("ix_patients_tenant_email", "patients", ["tenant_id", "email"])

    op.create_table(
        "location_working_hours",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column("start_local", sa.Time(), nullable=False),
        sa.Column("end_local", sa.Time(), nullable=False),
        sa.Column("slot_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("location_id", "weekday", name="uq_location_hours_weekday"),
        sa.CheckConstraint("weekday >= 0 AND weekday <= 6", name="ck_location_hours_weekday"),
        sa.CheckConstraint("end_local > start_local", name="ck_location_hours_range"),
        sa.CheckConstraint(
            "slot_minutes >= 5 AND slot_minutes <= 480", name="ck_location_hours_slot"
        ),
    )
    op.create_index("ix_location_hours_tenant", "location_working_hours", ["tenant_id"])
    op.create_index("ix_location_hours_location", "location_working_hours", ["location_id"])

    op.execute(
        sa.text("GRANT SELECT, INSERT, UPDATE, DELETE ON location_working_hours TO hos_app")
    )
    op.execute(sa.text("ALTER TABLE location_working_hours ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE location_working_hours FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            "CREATE POLICY location_working_hours_tenant_isolation ON location_working_hours "
            f"FOR ALL TO {APP_ROLE} USING (tenant_id = {SETTING}) "
            f"WITH CHECK (tenant_id = {SETTING})"
        )
    )

    for name, perms in ROLE_PERMS.items():
        op.execute(
            sa.text(
                "UPDATE roles SET permissions = CAST(:perms AS JSONB) "
                "WHERE tenant_id IS NULL AND name = :name"
            ).bindparams(perms=json.dumps(sorted(perms)), name=name)
        )


def downgrade() -> None:
    for name, perms in PRIOR_ROLE_PERMS.items():
        op.execute(
            sa.text(
                "UPDATE roles SET permissions = CAST(:perms AS JSONB) "
                "WHERE tenant_id IS NULL AND name = :name"
            ).bindparams(perms=json.dumps(sorted(perms)), name=name)
        )

    op.execute(
        sa.text(
            "DROP POLICY IF EXISTS location_working_hours_tenant_isolation "
            "ON location_working_hours"
        )
    )
    op.execute(sa.text("ALTER TABLE location_working_hours DISABLE ROW LEVEL SECURITY"))
    op.drop_index("ix_location_hours_location", table_name="location_working_hours")
    op.drop_index("ix_location_hours_tenant", table_name="location_working_hours")
    op.drop_table("location_working_hours")

    op.drop_index("ix_patients_tenant_email", table_name="patients")
    op.drop_index("ix_patients_tenant_phone", table_name="patients")
    op.drop_column("patients", "emergency_contact_phone")
    op.drop_column("patients", "emergency_contact_name")
    op.drop_column("patients", "date_of_birth")
    op.drop_column("patients", "email")
