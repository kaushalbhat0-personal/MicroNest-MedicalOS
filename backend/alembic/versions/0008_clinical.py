"""0008 clinical + dental data model.

Generic clinical: encounters, notes, observations (+catalog), diagnoses
(+catalog). Prescriptions: medication catalog + prescriptions/items.
Dental: condition/procedure catalogs, tooth findings (+surfaces), treatment
plans (+items), procedure records, consents, recalls, document references.

Catalogs are global read-only reference data (no tenant, no RLS — same
standing as the tenants registry; no write endpoints exist). All clinical
tables are tenant-owned, RLS-enforced, least-privilege granted.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008_clinical"
down_revision: str | Sequence[str] | None = "0007_scheduling"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "hos_app"
SETTING = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"

# Seed permission bundles (must match platform/authz/permissions.py).
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
]
ROLE_PERMS = {
    "tenant_admin": BASE_TENANT_ADMIN + CLINICAL_ADMIN,
    "doctor": ["tenant.read", "appointment.read", "appointment.update", "patient.read"]
    + CLINICAL_ADMIN,
    "receptionist": [
        "tenant.read",
        "appointment.read",
        "appointment.create",
        "appointment.update",
        "patient.read",
        "patient.create",
        "encounter.open",
        "encounter.read",
    ],
    "nurse": [
        "tenant.read",
        "appointment.read",
        "patient.read",
        "encounter.read",
        "clinical.read",
        "clinical.create",
    ],
}

# Frozen P2 bundles (downgrade path only).
P2_PERMS = {
    "tenant_admin": BASE_TENANT_ADMIN,
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

OBSERVATION_TYPES = [
    ("bp_systolic", "Blood pressure — systolic", "mmHg", 50, 300),
    ("bp_diastolic", "Blood pressure — diastolic", "mmHg", 30, 200),
    ("pulse", "Pulse rate", "bpm", 20, 300),
    ("temperature", "Body temperature", "°C", 30, 45),
    ("respiratory_rate", "Respiratory rate", "/min", 4, 80),
    ("spo2", "Oxygen saturation", "%", 50, 100),
    ("height", "Height", "cm", 30, 250),
    ("weight", "Weight", "kg", 1, 300),
]

DIAGNOSIS_CODES = [
    ("J06.9", "Acute upper respiratory infection", "J06.9", None, True),
    ("I10", "Essential hypertension", "I10", "38341003", False),
    ("E11.9", "Type 2 diabetes without complications", "E11.9", "44054006", False),
    ("K02.9", "Dental caries, unspecified", "K02.9", "80967001", False),
    ("K04.7", "Periapical abscess without sinus", "K04.7", "196472002", False),
    ("K05.30", "Chronic periodontitis", "K05.30", "41565005", False),
    ("K08.1", "Complete loss of teeth", "K08.1", "706780007", False),
    ("K21.9", "Gastro-oesophageal reflux disease", "K21.9", "235595009", False),
    ("J02.9", "Acute pharyngitis", "J02.9", "363746003", True),
    ("R50.9", "Fever, unspecified", "R50.9", "386661006", True),
    ("R51", "Headache", "R51", "25064002", True),
    ("Z00.6", "Encounter for clinical examination", "Z00.6", None, False),
]

MEDICATIONS = [
    ("amoxicillin-500", "Amoxicillin", "Amoxicillin", "500 mg", "capsule", "J01CA04"),
    ("ibuprofen-400", "Ibuprofen", "Ibuprofen", "400 mg", "tablet", "M01AE01"),
    ("paracetamol-650", "Paracetamol", "Paracetamol", "650 mg", "tablet", "N02BE01"),
    ("azithromycin-500", "Azithromycin", "Azithromycin", "500 mg", "tablet", "J01FA10"),
    ("metronidazole-400", "Metronidazole", "Metronidazole", "400 mg", "tablet", "J01XD01"),
    ("cetirizine-10", "Cetirizine", "Cetirizine", "10 mg", "tablet", "R06AE07"),
    ("omeprazole-20", "Omeprazole", "Omeprazole", "20 mg", "capsule", "A02BC01"),
    ("chlorhexidine-mw", "Chlorhexidine mouthwash", "Chlorhexidine", "0.2% w/v", "mouthwash", None),
    ("lignocaine-2", "Lignocaine injection", "Lignocaine", "2%", "injection", "N01BB02"),
    ("vitd3-60k", "Vitamin D3", "Cholecalciferol", "60000 IU", "sachet", "A11CC05"),
]

DENTAL_CONDITIONS = [
    ("caries", "Dental caries"),
    ("missing_tooth", "Missing tooth"),
    ("restoration", "Existing restoration"),
    ("fracture", "Tooth fracture"),
    ("mobility", "Tooth mobility"),
    ("sensitivity", "Dentine sensitivity"),
    ("periapical_abscess", "Periapical abscess"),
    ("periodontitis", "Periodontitis"),
    ("gingivitis", "Gingivitis"),
    ("crown", "Crown present"),
    ("root_canal_treated", "Root canal treated"),
    ("impaction", "Impacted tooth"),
    ("attrition", "Attrition"),
    ("erosion", "Erosion"),
    ("implant", "Implant present"),
]

DENTAL_PROCEDURES = [
    ("exam", "Clinical examination", "Routine oral examination", "general", None),
    ("cleaning", "Prophylaxis / cleaning", "Scaling and polishing", "hygiene", None),
    ("fluoride", "Fluoride application", "Topical fluoride", "preventive", None),
    ("xray_intraoral", "Intraoral X-ray", "Periapical/bitewing radiograph", "radiology", None),
    (
        "filling",
        "Restoration / filling",
        "Direct composite/amalgam restoration",
        "restorative",
        None,
    ),
    ("root_canal", "Root canal treatment", "Endodontic therapy", "endodontics", None),
    ("extraction", "Extraction", "Tooth removal", "surgery", None),
    ("crown_placement", "Crown placement", "Full-coverage restoration", "prosthodontics", None),
    ("implant_placement", "Implant placement", "Endosseous implant", "implantology", None),
    ("denture", "Denture fabrication", "Removable prosthesis", "prosthodontics", None),
    ("ortho_consult", "Orthodontic consultation", "Malocclusion assessment", "orthodontics", None),
    ("scaling", "Deep scaling", "Subgingival debridement", "periodontics", None),
]


def _enums() -> dict[str, postgresql.ENUM]:
    return {
        "encounter_status": postgresql.ENUM("open", "closed", name="encounter_status"),
        "note_status": postgresql.ENUM("draft", "finalized", "amended", name="note_status"),
        "diagnosis_status": postgresql.ENUM(
            "active", "resolved", "ruled_out", "superseded", name="diagnosis_status"
        ),
        "prescription_status": postgresql.ENUM(
            "draft", "signed", "cancelled", name="prescription_status"
        ),
        "finding_status": postgresql.ENUM("active", "resolved", name="finding_status"),
        "plan_status": postgresql.ENUM(
            "draft", "active", "completed", "cancelled", name="plan_status"
        ),
        "plan_item_status": postgresql.ENUM(
            "proposed",
            "planned",
            "in_progress",
            "completed",
            "cancelled",
            name="plan_item_status",
        ),
        "procedure_record_status": postgresql.ENUM(
            "planned",
            "in_progress",
            "completed",
            "cancelled",
            name="procedure_record_status",
        ),
        "consent_status": postgresql.ENUM(
            "pending", "granted", "declined", "withdrawn", name="consent_status"
        ),
        "recall_status": postgresql.ENUM(
            "scheduled", "completed", "cancelled", "missed", name="recall_status"
        ),
    }


TENANT_TABLES = [
    "encounters",
    "clinical_notes",
    "observations",
    "encounter_diagnoses",
    "prescriptions",
    "prescription_items",
    "tooth_findings",
    "tooth_finding_surfaces",
    "treatment_plans",
    "treatment_plan_items",
    "dental_procedure_records",
    "consents",
    "recalls",
    "document_references",
]

CATALOG_TABLES = [
    "observation_types",
    "diagnosis_codes",
    "medications",
    "dental_conditions",
    "dental_procedures",
]


def upgrade() -> None:
    E = _enums()

    # --- Global read-only catalogs (reference data, no RLS) ---
    op.create_table(
        "observation_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("display", sa.String(200), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("min_value", sa.Numeric(12, 3), nullable=True),
        sa.Column("max_value", sa.Numeric(12, 3), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "diagnosis_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("display", sa.String(300), nullable=False),
        sa.Column("icd10", sa.String(16), nullable=True),
        sa.Column("snomed", sa.String(32), nullable=True),
        sa.Column("needs_review", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "medications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("generic_name", sa.String(200), nullable=True),
        sa.Column("strength", sa.String(64), nullable=True),
        sa.Column("dosage_form", sa.String(64), nullable=True),
        sa.Column("atc", sa.String(16), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "dental_conditions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("display", sa.String(200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "dental_procedures",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("display", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("specialty", sa.String(40), nullable=False, server_default="general"),
        sa.Column("external_code", sa.String(32), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    # --- Tenant-owned clinical tables ---
    op.create_table(
        "encounters",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("practitioner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("chief_complaint", sa.String(500), nullable=True),
        sa.Column("status", E["encounter_status"], nullable=False, server_default="open"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("opened_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("opened_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("closed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("closed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("close_reason", sa.String(200), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["practitioner_id"], ["practitioners.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_encounters_tenant", "encounters", ["tenant_id"])
    op.create_index("ix_encounters_patient", "encounters", ["patient_id"])
    op.create_index("ix_encounters_practitioner", "encounters", ["practitioner_id"])
    op.create_index("ix_encounters_tenant_opened", "encounters", ["tenant_id", "opened_at", "id"])

    op.create_table(
        "clinical_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("note_type", sa.String(40), nullable=False, server_default="general"),
        sa.Column("chief_complaint", sa.String(500), nullable=True),
        sa.Column("subjective", sa.Text(), nullable=True),
        sa.Column("objective", sa.Text(), nullable=True),
        sa.Column("assessment", sa.Text(), nullable=True),
        sa.Column("plan", sa.Text(), nullable=True),
        sa.Column("status", E["note_status"], nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_addendum", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("superseded_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["encounter_id"], ["encounters.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["author_id"], ["practitioners.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supersedes_id"], ["clinical_notes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["superseded_by_id"], ["clinical_notes.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notes_tenant", "clinical_notes", ["tenant_id"])
    op.create_index("ix_notes_encounter", "clinical_notes", ["encounter_id"])

    op.create_table(
        "observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("value_numeric", sa.Numeric(12, 3), nullable=False),
        sa.Column("value_text", sa.String(200), nullable=True),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("taken_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("recorded_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("corrects_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("corrected_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["encounter_id"], ["encounters.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["type_id"], ["observation_types.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["corrects_id"], ["observations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["corrected_by_id"], ["observations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_observations_tenant", "observations", ["tenant_id"])
    op.create_index("ix_observations_encounter", "observations", ["encounter_id"])

    op.create_table(
        "encounter_diagnoses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("diagnosis_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("free_text", sa.String(300), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("status", E["diagnosis_status"], nullable=False, server_default="active"),
        sa.Column("review_needed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("onset_date", sa.Date(), nullable=True),
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("superseded_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recorded_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["encounter_id"], ["encounters.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["diagnosis_id"], ["diagnosis_codes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supersedes_id"], ["encounter_diagnoses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["superseded_by_id"], ["encounter_diagnoses.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "(diagnosis_id IS NULL) <> (free_text IS NULL)",
            name="ck_encdx_coded_xor_free",
        ),
    )
    op.create_index("ix_encdx_tenant", "encounter_diagnoses", ["tenant_id"])
    op.create_index("ix_encdx_encounter", "encounter_diagnoses", ["encounter_id"])

    op.create_table(
        "prescriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prescribed_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", E["prescription_status"], nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("superseded_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("signed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("signed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("cancelled_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cancelled_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.String(200), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["encounter_id"], ["encounters.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["prescribed_by"], ["practitioners.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supersedes_id"], ["prescriptions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["superseded_by_id"], ["prescriptions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rx_tenant", "prescriptions", ["tenant_id"])
    op.create_index("ix_rx_encounter", "prescriptions", ["encounter_id"])

    op.create_table(
        "prescription_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prescription_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("medication_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("dose", sa.String(64), nullable=False),
        sa.Column("route", sa.String(32), nullable=False),
        sa.Column("frequency", sa.String(64), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["prescription_id"], ["prescriptions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["medication_id"], ["medications.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rx_items_rx", "prescription_items", ["prescription_id"])

    op.create_table(
        "tooth_findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("practitioner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tooth", sa.Integer(), nullable=False),
        sa.Column("condition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", E["finding_status"], nullable=False, server_default="active"),
        sa.Column("details", sa.String(500), nullable=True),
        sa.Column("recorded_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["encounter_id"], ["encounters.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["practitioner_id"], ["practitioners.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["condition_id"], ["dental_conditions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_findings_tenant", "tooth_findings", ["tenant_id"])
    op.create_index("ix_findings_encounter", "tooth_findings", ["encounter_id"])
    op.create_index("ix_findings_tooth", "tooth_findings", ["tenant_id", "tooth"])

    op.create_table(
        "tooth_finding_surfaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("finding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("surface", sa.String(16), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["finding_id"], ["tooth_findings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("finding_id", "surface", name="uq_finding_surface"),
    )
    op.create_index("ix_finding_surfaces_finding", "tooth_finding_surfaces", ["finding_id"])

    op.create_table(
        "treatment_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("practitioner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", E["plan_status"], nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["encounter_id"], ["encounters.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["practitioner_id"], ["practitioners.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plans_tenant", "treatment_plans", ["tenant_id"])
    op.create_index("ix_plans_patient", "treatment_plans", ["patient_id"])

    op.create_table(
        "treatment_plan_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("procedure_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tooth", sa.Integer(), nullable=True),
        sa.Column("surface", sa.String(16), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", E["plan_item_status"], nullable=False, server_default="proposed"),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["treatment_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["procedure_id"], ["dental_procedures.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plan_items_plan", "treatment_plan_items", ["plan_id"])

    op.create_table(
        "dental_procedure_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("practitioner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("procedure_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_item_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tooth", sa.Integer(), nullable=True),
        sa.Column("surface", sa.String(16), nullable=True),
        sa.Column("status", E["procedure_record_status"], nullable=False, server_default="planned"),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("performed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["encounter_id"], ["encounters.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["practitioner_id"], ["practitioners.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["procedure_id"], ["dental_procedures.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["plan_item_id"], ["treatment_plan_items.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_procrec_tenant", "dental_procedure_records", ["tenant_id"])
    op.create_index("ix_procrec_encounter", "dental_procedure_records", ["encounter_id"])

    op.create_table(
        "consents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("procedure_record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", E["consent_status"], nullable=False, server_default="pending"),
        sa.Column("consenter_name", sa.String(200), nullable=False),
        sa.Column("consenter_relation", sa.String(64), nullable=True),
        sa.Column("document_ref", sa.String(500), nullable=True),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["treatment_plans.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["procedure_record_id"], ["dental_procedure_records.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "(plan_id IS NULL) <> (procedure_record_id IS NULL)",
            name="ck_consent_single_subject",
        ),
    )
    op.create_index("ix_consents_tenant", "consents", ["tenant_id"])

    op.create_table(
        "recalls",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("practitioner_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(200), nullable=False),
        sa.Column("status", E["recall_status"], nullable=False, server_default="scheduled"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["practitioner_id"], ["practitioners.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recalls_tenant", "recalls", ["tenant_id"])
    op.create_index("ix_recalls_patient", "recalls", ["patient_id"])
    op.create_index("ix_recalls_due", "recalls", ["tenant_id", "due_date"])

    op.create_table(
        "document_references",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("doc_type", sa.String(32), nullable=False, server_default="other"),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("content_type", sa.String(127), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["encounter_id"], ["encounters.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_docrefs_tenant", "document_references", ["tenant_id"])
    op.create_index("ix_docrefs_encounter", "document_references", ["encounter_id"])

    # --- Catalog seeds (reference data, no secrets) ---
    for code, display, unit, low, high in OBSERVATION_TYPES:
        op.execute(
            sa.text(
                "INSERT INTO observation_types "
                "(id, code, display, unit, min_value, max_value, is_active) "
                "VALUES (gen_random_uuid(), :code, :display, :unit, :low, :high, true)"
            ).bindparams(code=code, display=display, unit=unit, low=low, high=high)
        )
    for code, display, icd10, snomed, review in DIAGNOSIS_CODES:
        op.execute(
            sa.text(
                "INSERT INTO diagnosis_codes "
                "(id, code, display, icd10, snomed, needs_review, is_active) "
                "VALUES (gen_random_uuid(), :code, :display, :icd10, :snomed, :review, true)"
            ).bindparams(code=code, display=display, icd10=icd10, snomed=snomed, review=review)
        )
    for code, name, generic, strength, form, atc in MEDICATIONS:
        op.execute(
            sa.text(
                "INSERT INTO medications "
                "(id, code, name, generic_name, strength, dosage_form, atc, is_active) "
                "VALUES (gen_random_uuid(), :code, :name, :generic, :strength, :form, :atc, true)"
            ).bindparams(
                code=code, name=name, generic=generic, strength=strength, form=form, atc=atc
            )
        )
    for code, display in DENTAL_CONDITIONS:
        op.execute(
            sa.text(
                "INSERT INTO dental_conditions (id, code, display, is_active) "
                "VALUES (gen_random_uuid(), :code, :display, true)"
            ).bindparams(code=code, display=display)
        )
    for code, display, desc, specialty, ext in DENTAL_PROCEDURES:
        op.execute(
            sa.text(
                "INSERT INTO dental_procedures "
                "(id, code, display, description, specialty, external_code, is_active) "
                "VALUES (gen_random_uuid(), :code, :display, :desc, :specialty, :ext, true)"
            ).bindparams(code=code, display=display, desc=desc, specialty=specialty, ext=ext)
        )

    # --- Seed role bundles grow P3 clinical permissions ---
    import json as _json

    for name, perms in ROLE_PERMS.items():
        op.execute(
            sa.text(
                "UPDATE roles SET permissions = CAST(:perms AS JSONB) "
                "WHERE tenant_id IS NULL AND name = :name"
            ).bindparams(name=name, perms=_json.dumps(sorted(perms)))
        )

    # --- Grants + RLS ---
    for table in CATALOG_TABLES:
        op.execute(sa.text(f"GRANT SELECT ON {table} TO {APP_ROLE}"))
    for table in TENANT_TABLES:
        op.execute(sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}"))
    op.execute(sa.text(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}"))
    for table in TENANT_TABLES:
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
    import json as _json

    for name, perms in P2_PERMS.items():
        op.execute(
            sa.text(
                "UPDATE roles SET permissions = CAST(:perms AS JSONB) "
                "WHERE tenant_id IS NULL AND name = :name"
            ).bindparams(name=name, perms=_json.dumps(sorted(perms)))
        )
    for table in TENANT_TABLES:
        op.execute(sa.text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
        op.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))
    for table in reversed(TENANT_TABLES):
        op.execute(sa.text(f"DROP TABLE {table}"))
    for table in CATALOG_TABLES:
        op.execute(sa.text(f"DROP TABLE {table}"))
    for enum_name in (
        "encounter_status",
        "note_status",
        "diagnosis_status",
        "prescription_status",
        "finding_status",
        "plan_status",
        "plan_item_status",
        "procedure_record_status",
        "consent_status",
        "recall_status",
    ):
        postgresql.ENUM(name=enum_name).drop(op.get_bind(), checkfirst=True)
