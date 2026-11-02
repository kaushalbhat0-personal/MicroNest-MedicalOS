"""Central permission catalog. Platform-defined strings; tenant roles are
bundles of these. Downstream-domain permissions are DECLARED here so P2+
endpoints can reference them, but no enforcement points exist yet outside P1.

Constitution: no `if user.role == "admin"` scattered in code. Every protected
endpoint declares `require("<permission>")`.
"""

from app.platform.errors import ValidationError


class P:
    # P1: platform / tenant administration
    PLATFORM_TENANT_CREATE = "platform.tenant.create"
    PLATFORM_TENANT_SUSPEND = "platform.tenant.suspend"
    PLATFORM_HEALTH = "platform.health"
    TENANT_READ = "tenant.read"
    TENANT_SETTINGS = "settings.manage"
    STAFF_INVITE = "staff.invite"
    STAFF_MANAGE = "staff.manage"
    ROLES_MANAGE = "roles.manage"
    LOCATIONS_MANAGE = "locations.manage"
    AUDIT_READ = "audit.read"
    SUPPORT_GRANT = "support.grant"  # defined; granting flow is P5+

    # Declared for P2+ (no enforcement points yet)
    PATIENT_READ = "patient.read"
    PATIENT_CREATE = "patient.create"
    PATIENT_UPDATE = "patient.update"
    APPOINTMENT_READ = "appointment.read"
    APPOINTMENT_CREATE = "appointment.create"
    APPOINTMENT_UPDATE = "appointment.update"
    SCHEDULE_MANAGE = "schedule.manage"
    QUEUE_MANAGE = "queue.manage"
    ENCOUNTER_OPEN = "encounter.open"
    ENCOUNTER_CLOSE = "encounter.close"
    ENCOUNTER_READ = "encounter.read"
    CLINICAL_READ = "clinical.read"
    CLINICAL_CREATE = "clinical.create"
    PRESCRIPTION_READ = "prescription.read"
    PRESCRIPTION_CREATE = "prescription.create"
    PRESCRIPTION_SIGN = "prescription.sign"
    DENTAL_READ = "dental.read"
    DENTAL_RECORD = "dental.record"
    PLAN_MANAGE = "plan.manage"
    BILLING_READ = "billing.read"
    BILLING_CREATE = "billing.create"
    INVOICE_ISSUE = "invoice.issue"
    PAYMENT_RECORD = "payment.record"
    INVENTORY_READ = "inventory.read"
    INVENTORY_ADJUST = "inventory.adjust"
    DOCUMENT_READ = "documents.read"
    DOCUMENT_UPLOAD = "documents.upload"
    BRANDING_MANAGE = "branding.manage"
    REPORTS_VIEW = "reports.view"
    REPORTS_EXPORT = "reports.export"


CLINICAL_ADMIN = frozenset(
    {
        P.ENCOUNTER_OPEN,
        P.ENCOUNTER_CLOSE,
        P.ENCOUNTER_READ,
        P.CLINICAL_READ,
        P.CLINICAL_CREATE,
        P.PRESCRIPTION_READ,
        P.PRESCRIPTION_CREATE,
        P.PRESCRIPTION_SIGN,
        P.DENTAL_READ,
        P.DENTAL_RECORD,
        P.PLAN_MANAGE,
    }
)


# Seed role bundles. Tenant admins may define custom roles (subset only —
# custom roles can never include platform.* permissions).
SEED_ROLES: dict[str, frozenset[str]] = {
    "platform_admin": frozenset(
        {P.PLATFORM_TENANT_CREATE, P.PLATFORM_TENANT_SUSPEND, P.PLATFORM_HEALTH}
    ),
    "tenant_admin": frozenset(
        {
            P.TENANT_READ,
            P.TENANT_SETTINGS,
            P.STAFF_INVITE,
            P.STAFF_MANAGE,
            P.ROLES_MANAGE,
            P.LOCATIONS_MANAGE,
            P.AUDIT_READ,
            P.APPOINTMENT_READ,
            P.APPOINTMENT_CREATE,
            P.APPOINTMENT_UPDATE,
            P.PATIENT_READ,
            P.PATIENT_CREATE,
            *CLINICAL_ADMIN,
        }
    ),
    "doctor": frozenset(
        {P.TENANT_READ, P.APPOINTMENT_READ, P.APPOINTMENT_UPDATE, P.PATIENT_READ, *CLINICAL_ADMIN}
    ),
    "receptionist": frozenset(
        {
            P.TENANT_READ,
            P.APPOINTMENT_READ,
            P.APPOINTMENT_CREATE,
            P.APPOINTMENT_UPDATE,
            P.PATIENT_READ,
            P.PATIENT_CREATE,
            P.ENCOUNTER_OPEN,
            P.ENCOUNTER_READ,
        }
    ),
    "nurse": frozenset(
        {
            P.TENANT_READ,
            P.APPOINTMENT_READ,
            P.PATIENT_READ,
            P.ENCOUNTER_READ,
            P.CLINICAL_READ,
            P.CLINICAL_CREATE,
        }
    ),
    "accountant": frozenset({P.TENANT_READ}),
    "staff": frozenset({P.TENANT_READ}),
    "patient": frozenset(),
}

# Permissions a tenant custom role may never contain.
PLATFORM_ONLY = frozenset(
    {P.PLATFORM_TENANT_CREATE, P.PLATFORM_TENANT_SUSPEND, P.PLATFORM_HEALTH, P.SUPPORT_GRANT}
)


def validate_custom_role(permissions: list[str]) -> None:
    unknown = set(permissions) - {v for v in vars(P).values() if isinstance(v, str)}
    if unknown:
        raise ValidationError(f"unknown permissions: {sorted(unknown)}")
    if set(permissions) & PLATFORM_ONLY:
        raise ValidationError("custom roles cannot include platform permissions")
