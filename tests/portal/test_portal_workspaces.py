"""Portal workspaces routing signal: provider vs portal availability per identity."""

from app.modules.portal import service as portal_service
from tests.helpers import login_client, provision_scheduling, tenant_headers
from tests.portal.test_portal_security import _enroll


def test_staff_user_is_provider_only(client, owner_db, make_owner_user, make_tenant):
    from tests.helpers import provision_clinical

    provision_clinical(
        owner_db,
        make_owner_user,
        make_tenant,
        slug="ws-staff",
        admin_email="ws-staff@example.com",
    )
    c = login_client(client, email="ws-staff@example.com")
    r = c.get("/api/v1/portal/workspaces")
    assert r.status_code == 200, r.text
    assert r.json() == {"provider": True, "portal": False}


def test_portal_only_user_routes_to_portal(
    client, owner_db, make_owner_user, make_tenant
):
    a = provision_scheduling(
        owner_db,
        make_owner_user,
        make_tenant,
        slug="ws-pat",
        admin_email="ws-pat@example.com",
    )
    _enroll(client, a, email="ws-portal@example.com")
    from app.modules.identity import service as identity_service

    user = identity_service.get_user_by_email(owner_db, "ws-portal@example.com")
    identity_service.set_password(owner_db, user, "ws-portal-pass-1")
    owner_db.commit()
    c = login_client(client, email="ws-portal@example.com", password="ws-portal-pass-1")
    r = c.get("/api/v1/portal/workspaces")
    assert r.status_code == 200, r.text
    assert r.json() == {"provider": False, "portal": True}


def test_dual_user_keeps_provider(client, owner_db, make_owner_user, make_tenant):
    from tests.helpers import provision_clinical, provision_scheduling

    b = provision_clinical(
        owner_db,
        make_owner_user,
        make_tenant,
        slug="ws-dual",
        admin_email="ws-dual@example.com",
    )
    # Same staff user also enrolled as a patient in a second tenant
    # (enrolled by that tenant's own admin).
    b2 = provision_scheduling(
        owner_db,
        make_owner_user,
        make_tenant,
        slug="ws-dual-b",
        admin_email="ws-dual-b@example.com",
    )
    admin_b = login_client(client, email="ws-dual-b@example.com")
    from app.modules.patients import service as patients_service

    patient = patients_service.register_patient(
        owner_db, tenant_id=b2["tenant"].id, display_name="Dual User"
    )
    owner_db.commit()
    resp = admin_b.post(
        f"/api/v1/tenants/{b2['tenant'].id}/portal-links",
        headers=tenant_headers(str(b2["tenant"].id)),
        json={"email": "ws-dual@example.com", "patient_id": str(patient.id)},
    )
    assert resp.status_code == 200, resp.text
    # Membership in the second tenant is patient-role; staff membership remains.
    dual = login_client(client, email="ws-dual@example.com")
    r = dual.get(
        "/api/v1/portal/workspaces", headers=tenant_headers(str(b["tenant"].id))
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"provider": True, "portal": True}


def test_user_without_access_gets_neither(client, owner_db, make_owner_user):
    make_owner_user(email="ws-none@example.com")
    owner_db.commit()
    c = login_client(client, email="ws-none@example.com")
    assert c.get("/api/v1/portal/workspaces").json() == {
        "provider": False,
        "portal": False,
    }


def test_workspaces_requires_login(client):
    assert client.get("/api/v1/portal/workspaces").status_code == 401


def test_revoked_link_removes_portal_workspace(
    client, owner_db, make_owner_user, make_tenant
):
    a = provision_scheduling(
        owner_db,
        make_owner_user,
        make_tenant,
        slug="ws-rev",
        admin_email="ws-rev@example.com",
    )
    link = _enroll(client, a, email="ws-rev-portal@example.com")
    admin = login_client(client, email="ws-rev@example.com")
    r = admin.delete(
        f"/api/v1/tenants/{a['tenant'].id}/portal-links/{link['id']}",
        headers=tenant_headers(str(a["tenant"].id)),
    )
    assert r.status_code == 200, r.text
    from app.modules.identity import service as identity_service

    user = identity_service.get_user_by_email(owner_db, "ws-rev-portal@example.com")
    assert portal_service.workspaces_for_user(owner_db, user_id=user.id) == {
        "provider": False,
        "portal": False,
    }
