"""Shared provisioning helpers for API/isolation tests.

owner_db sessions bypass RLS as table owner (migrations/seeds path);
the HTTP client always runs through the app role (RLS-enforced).
"""

import uuid

from fastapi.testclient import TestClient


def make_platform_admin(owner_db, make_owner_user, *, email: str | None = None):  # type: ignore[no-untyped-def]
    admin = make_owner_user(email=email or f"root-{uuid.uuid4().hex[:6]}@example.com")
    admin.is_platform_admin = True
    owner_db.commit()
    return admin


def provision_tenant(
    owner_db,
    make_owner_user,
    make_tenant,
    *,
    slug: str | None = None,
    admin_email: str | None = None,
):  # type: ignore[no-untyped-def]
    """Create tenant + location + tenant_admin membership. Returns dict."""
    from app.modules.clinics import service as clinics_service
    from app.modules.tenancy import service as tenancy_service

    admin = make_owner_user(
        email=admin_email or f"admin-{uuid.uuid4().hex[:6]}@example.com"
    )
    tenant = make_tenant(slug=slug)
    location = clinics_service.create_location(
        owner_db, tenant=tenant, name="Main Clinic"
    )
    role = tenancy_service.get_seed_role(owner_db, "tenant_admin")
    tenancy_service.create_membership(
        owner_db, user=admin, tenant=tenant, role=role, is_primary=True
    )
    owner_db.commit()
    return {"tenant": tenant, "admin": admin, "location": location}


def login_client(
    base_client: TestClient, *, email: str, password: str = "password-12345-abc"
) -> TestClient:
    fresh = TestClient(base_client.app, base_url="http://test")
    resp = fresh.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return fresh


def tenant_headers(tenant_id: object) -> dict[str, str]:
    return {"X-Tenant": str(tenant_id)}


def provision_scheduling(
    owner_db,
    make_owner_user,
    make_tenant,
    *,
    slug: str | None = None,
    admin_email: str | None = None,
    practitioner_name: str = "Dr Sched",
    patient_name: str = "Pat Sched",
    patient_phone: str | None = "+911234567890",
):  # type: ignore[no-untyped-def]
    """Tenant + admin + location + approved practitioner + patient. Returns dict."""
    from app.modules.patients import service as patients_service
    from app.modules.tenancy import service as tenancy_service

    base = provision_tenant(
        owner_db, make_owner_user, make_tenant, slug=slug, admin_email=admin_email
    )
    tenant = base["tenant"]
    practitioner = tenancy_service.register_practitioner(
        owner_db, display_name=practitioner_name
    )
    tenancy_service.set_verification(
        owner_db, tenant=tenant, practitioner=practitioner, status="approved"
    )
    patient = patients_service.register_patient(
        owner_db,
        tenant_id=tenant.id,
        display_name=patient_name,
        phone=patient_phone,
    )
    owner_db.commit()
    return {**base, "practitioner": practitioner, "patient": patient}


def provision_clinical(
    owner_db,
    make_owner_user,
    make_tenant,
    *,
    slug: str | None = None,
    admin_email: str | None = None,
    doctor_email: str | None = None,
    practitioner_name: str = "Dr Clinical",
    patient_name: str = "Pat Clinical",
):  # type: ignore[no-untyped-def]
    """Tenant + admin + doctor (user-linked, approved practitioner) + patient."""
    from app.modules.patients import service as patients_service
    from app.modules.tenancy import service as tenancy_service

    base = provision_tenant(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=slug,
        admin_email=admin_email,
    )
    tenant = base["tenant"]
    doctor = make_owner_user(
        email=doctor_email or f"doc-{uuid.uuid4().hex[:6]}@example.com"
    )
    practitioner = tenancy_service.register_practitioner(
        owner_db, display_name=practitioner_name, user=doctor
    )
    tenancy_service.set_verification(
        owner_db, tenant=tenant, practitioner=practitioner, status="approved"
    )
    tenancy_service.create_membership(
        owner_db,
        user=doctor,
        tenant=tenant,
        role=tenancy_service.get_seed_role(owner_db, "doctor"),
    )
    patient = patients_service.register_patient(
        owner_db, tenant_id=tenant.id, display_name=patient_name
    )
    owner_db.commit()
    return {**base, "doctor": doctor, "practitioner": practitioner, "patient": patient}
