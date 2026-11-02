"""0007 scheduling (patients + appointments) + deferred P1 FK indexes.

- `patients`: minimal tenant-scoped identity (no clinical data).
- `appointments`: practitioner commitments with UTC instants; status is a
  native enum (stable P2+ state machine). Double-booking is prevented by a
  transaction-scoped advisory lock + overlap check in the service (portable
  across managed/private/on-prem Postgres without contrib extensions).
- Deferred from P1.1: single-column FK indexes that 0001-0005 omitted.
- Seed role bundles grow the P2 scheduling permissions (reference data only).
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007_scheduling"
down_revision: str | Sequence[str] | None = "0006_audit_seq"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


APP_ROLE = "hos_app"
SETTING = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"

STATUSES = (
    "scheduled",
    "confirmed",
    "checked_in",
    "completed",
    "cancelled",
    "no_show",
)

APPOINTMENT_PERMS = {
    "tenant_admin": [
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
    ],
    "doctor": ["tenant.read", "appointment.read", "appointment.update", "patient.read"],
    "receptionist": [
        "tenant.read",
        "appointment.read",
        "appointment.create",
        "appointment.update",
        "patient.read",
        "patient.create",
    ],
    "nurse": ["tenant.read", "appointment.read", "patient.read"],
}

# Frozen P1 bundles (for a clean downgrade path only).
P1_PERMS = {
    "tenant_admin": [
        "tenant.read",
        "settings.manage",
        "staff.invite",
        "staff.manage",
        "roles.manage",
        "locations.manage",
        "audit.read",
    ],
    "doctor": ["tenant.read"],
    "receptionist": ["tenant.read"],
    "nurse": ["tenant.read"],
}

# Deferred single-column FK indexes (P1.1 finding, applied here).
FK_INDEXES = [
    ("ix_locations_tenant", "locations", ["tenant_id"]),
    ("ix_memberships_role", "memberships", ["role_id"]),
    ("ix_invitations_tenant", "invitations", ["tenant_id"]),
    ("ix_invitations_role", "invitations", ["role_id"]),
    ("ix_invitations_invited_by", "invitations", ["invited_by"]),
    ("ix_verifications_practitioner", "practitioner_verifications", ["practitioner_id"]),
    ("ix_verifications_reviewer", "practitioner_verifications", ["reviewer_id"]),
    ("ix_membership_locations_location", "membership_locations", ["location_id"]),
]


def upgrade() -> None:
    # NOTE: no explicit CREATE TYPE — `op.create_table` emits it for the
    # native enum below. Pre-creating AND referencing it double-creates.
    appointment_status = postgresql.ENUM(*STATUSES, name="appointment_status")

    op.create_table(
        "patients",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_patients_tenant", "patients", ["tenant_id"])

    op.create_table(
        "appointments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("practitioner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("start_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("end_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Kolkata"),
        sa.Column(
            "status",
            appointment_status,
            nullable=False,
            server_default="scheduled",
        ),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("idempotency_key", sa.String(64), nullable=True),
        sa.Column("cancelled_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("cancelled_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cancel_reason", sa.String(200), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["practitioner_id"], ["practitioners.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("end_at > start_at", name="ck_appointments_end_after_start"),
    )
    op.create_index("ix_appointments_tenant", "appointments", ["tenant_id"])
    op.create_index("ix_appointments_patient", "appointments", ["patient_id"])
    op.create_index("ix_appointments_practitioner", "appointments", ["practitioner_id"])
    op.create_index("ix_appointments_location", "appointments", ["location_id"])
    op.create_index("ix_appointments_tenant_start", "appointments", ["tenant_id", "start_at", "id"])
    op.create_index(
        "uq_appointments_tenant_idem",
        "appointments",
        ["tenant_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    for name, table, cols in FK_INDEXES:
        op.create_index(name, table, cols)

    # Seed bundles grow scheduling permissions (reference data, no secrets).
    for name, perms in APPOINTMENT_PERMS.items():
        op.execute(
            sa.text(
                "UPDATE roles SET permissions = CAST(:perms AS JSONB) "
                "WHERE tenant_id IS NULL AND name = :name"
            ).bindparams(name=name, perms=json.dumps(sorted(perms)))
        )

    for table in ("patients", "appointments"):
        op.execute(sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}"))
    op.execute(sa.text(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}"))
    for table in ("patients", "appointments"):
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                f"CREATE POLICY {table}_tenant_isolation ON {table} "
                f"FOR ALL TO {APP_ROLE} USING (tenant_id = {SETTING}) "
                f"WITH CHECK (tenant_id = {SETTING})"
            )
        )


def downgrade() -> None:
    for name, perms in P1_PERMS.items():
        op.execute(
            sa.text(
                "UPDATE roles SET permissions = CAST(:perms AS JSONB) "
                "WHERE tenant_id IS NULL AND name = :name"
            ).bindparams(name=name, perms=json.dumps(sorted(perms)))
        )
    for table in ("patients", "appointments"):
        op.execute(sa.text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
        op.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))
    for name, table, _cols in FK_INDEXES:
        op.drop_index(name, table_name=table)
    op.drop_index("uq_appointments_tenant_idem", table_name="appointments")
    op.drop_index("ix_appointments_tenant_start", table_name="appointments")
    op.drop_index("ix_appointments_location", table_name="appointments")
    op.drop_index("ix_appointments_practitioner", table_name="appointments")
    op.drop_index("ix_appointments_patient", table_name="appointments")
    op.drop_index("ix_appointments_tenant", table_name="appointments")
    op.drop_table("appointments")
    op.drop_index("ix_patients_tenant", table_name="patients")
    op.drop_table("patients")
    postgresql.ENUM(name="appointment_status").drop(op.get_bind(), checkfirst=True)
