"""0020 follow-ups, communication consents, communication logs + seed perms.

Additive tables with tenant RLS. Seed role growth for follow-up and
communication permissions. No automated messaging.
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0020_followups_comms"
down_revision: str | Sequence[str] | None = "0019_queue_tokens"
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
COMMS = [
    "followup.read",
    "followup.manage",
    "communication.read",
    "communication.log",
    "communication.consent.manage",
]

ROLE_PERMS = {
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
        "patient.update",
        *CLINICAL_ADMIN,
        *BILLING_FULL,
        *COMMS,
    ],
    "doctor": [
        "tenant.read",
        "appointment.read",
        "appointment.update",
        "patient.read",
        *CLINICAL_ADMIN,
        "billing.read",
        "billing.create",
        *COMMS,
    ],
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
        *COMMS,
    ],
    "nurse": [
        "tenant.read",
        "appointment.read",
        "patient.read",
        "encounter.read",
        "clinical.read",
        "clinical.create",
        "followup.read",
        "followup.manage",
        "communication.read",
        "communication.log",
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

# Frozen 0019 / post-0018 seed bundles for downgrade.
PRIOR_ROLE_PERMS = {
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
        "patient.update",
        *CLINICAL_ADMIN,
        *BILLING_FULL,
    ],
    "doctor": [
        "tenant.read",
        "appointment.read",
        "appointment.update",
        "patient.read",
        *CLINICAL_ADMIN,
        "billing.read",
        "billing.create",
    ],
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

def _enums() -> dict[str, postgresql.ENUM]:
    return {
        "followup_category": postgresql.ENUM(
            "encounter",
            "treatment_plan",
            "prescription",
            "appointment",
            "manual",
            "other",
            name="followup_category",
        ),
        "followup_source_type": postgresql.ENUM(
            "encounter",
            "treatment_plan",
            "prescription",
            "appointment",
            "manual",
            name="followup_source_type",
        ),
        "followup_priority": postgresql.ENUM(
            "low", "normal", "high", "urgent", name="followup_priority"
        ),
        "followup_status": postgresql.ENUM(
            "open",
            "in_progress",
            "snoozed",
            "completed",
            "cancelled",
            name="followup_status",
        ),
        "comm_consent_channel": postgresql.ENUM(
            "phone", "email", "whatsapp", "sms", name="comm_consent_channel"
        ),
        "comm_consent_purpose": postgresql.ENUM(
            "appointment_reminder",
            "care_followup",
            "administrative",
            "marketing",
            name="comm_consent_purpose",
        ),
        "comm_consent_status": postgresql.ENUM(
            "granted", "denied", "revoked", name="comm_consent_status"
        ),
        "comm_consent_capture": postgresql.ENUM(
            "staff", "portal", "import", "other", name="comm_consent_capture"
        ),
        "comm_log_channel": postgresql.ENUM(
            "phone",
            "email",
            "whatsapp",
            "sms",
            "in_person",
            "other",
            name="comm_log_channel",
        ),
        "comm_log_purpose": postgresql.ENUM(
            "appointment_reminder",
            "care_followup",
            "administrative",
            "marketing",
            name="comm_log_purpose",
        ),
        "comm_log_outcome": postgresql.ENUM(
            "contacted",
            "no_answer",
            "callback_requested",
            "declined",
            "incorrect_contact",
            "follow_up_scheduled",
            name="comm_log_outcome",
        ),
    }


RLS_TABLES = ("follow_ups", "communication_consents", "communication_logs")
ENUM_NAMES = (
    "comm_log_outcome",
    "comm_log_purpose",
    "comm_log_channel",
    "comm_consent_capture",
    "comm_consent_status",
    "comm_consent_purpose",
    "comm_consent_channel",
    "followup_status",
    "followup_priority",
    "followup_source_type",
    "followup_category",
)


def upgrade() -> None:
    E = _enums()

    op.create_table(
        "follow_ups",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("due_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("category", E["followup_category"], nullable=False),
        sa.Column("reason", sa.String(length=200), nullable=False),
        sa.Column("source_type", E["followup_source_type"], nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("priority", E["followup_priority"], nullable=False),
        sa.Column("status", E["followup_status"], nullable=False),
        sa.Column("outcome", sa.String(length=64), nullable=True),
        sa.Column("next_action", sa.String(length=200), nullable=True),
        sa.Column("next_due_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("snooze_until", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("completed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_followups_tenant", "follow_ups", ["tenant_id"])
    op.create_index("ix_followups_patient", "follow_ups", ["patient_id"])
    op.create_index("ix_followups_due", "follow_ups", ["tenant_id", "due_at"])
    op.create_index("ix_followups_assignee", "follow_ups", ["tenant_id", "assigned_user_id"])
    op.create_index("ix_followups_status", "follow_ups", ["tenant_id", "status"])
    op.create_index(
        "uq_followups_active_source",
        "follow_ups",
        ["tenant_id", "source_type", "source_id", "category"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('open', 'in_progress', 'snoozed') AND source_id IS NOT NULL"
        ),
    )

    op.create_table(
        "communication_consents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", E["comm_consent_channel"], nullable=False),
        sa.Column("purpose", E["comm_consent_purpose"], nullable=False),
        sa.Column("status", E["comm_consent_status"], nullable=False),
        sa.Column("capture_source", E["comm_consent_capture"], nullable=False),
        sa.Column("recorded_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("captured_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revoked_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("superseded_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["superseded_by_id"], ["communication_consents.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_comm_consent_tenant", "communication_consents", ["tenant_id"])
    op.create_index("ix_comm_consent_patient", "communication_consents", ["patient_id"])
    op.create_index(
        "uq_comm_consent_current",
        "communication_consents",
        ["tenant_id", "patient_id", "channel", "purpose"],
        unique=True,
        postgresql_where=sa.text("is_current IS TRUE"),
    )

    op.create_table(
        "communication_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("follow_up_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("channel", E["comm_log_channel"], nullable=False),
        sa.Column("purpose", E["comm_log_purpose"], nullable=False),
        sa.Column("outcome", E["comm_log_outcome"], nullable=False),
        sa.Column("staff_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("note", sa.String(length=280), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["follow_up_id"], ["follow_ups.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["staff_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_comm_logs_tenant", "communication_logs", ["tenant_id"])
    op.create_index("ix_comm_logs_patient", "communication_logs", ["patient_id"])
    op.create_index("ix_comm_logs_followup", "communication_logs", ["follow_up_id"])
    op.create_index(
        "ix_comm_logs_occurred", "communication_logs", ["tenant_id", "occurred_at"]
    )

    for table in RLS_TABLES:
        op.execute(sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}"))
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                f"CREATE POLICY {table}_tenant_isolation ON {table} "
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

    for table in RLS_TABLES:
        op.execute(sa.text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
        op.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))

    op.drop_index("ix_comm_logs_occurred", table_name="communication_logs")
    op.drop_index("ix_comm_logs_followup", table_name="communication_logs")
    op.drop_index("ix_comm_logs_patient", table_name="communication_logs")
    op.drop_index("ix_comm_logs_tenant", table_name="communication_logs")
    op.drop_table("communication_logs")

    op.drop_index("uq_comm_consent_current", table_name="communication_consents")
    op.drop_index("ix_comm_consent_patient", table_name="communication_consents")
    op.drop_index("ix_comm_consent_tenant", table_name="communication_consents")
    op.drop_table("communication_consents")

    op.drop_index("uq_followups_active_source", table_name="follow_ups")
    op.drop_index("ix_followups_status", table_name="follow_ups")
    op.drop_index("ix_followups_assignee", table_name="follow_ups")
    op.drop_index("ix_followups_due", table_name="follow_ups")
    op.drop_index("ix_followups_patient", table_name="follow_ups")
    op.drop_index("ix_followups_tenant", table_name="follow_ups")
    op.drop_table("follow_ups")

    for enum_name in ENUM_NAMES:
        postgresql.ENUM(name=enum_name).drop(op.get_bind(), checkfirst=True)
