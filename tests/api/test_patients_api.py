"""Patient CRM API: register, search, update, import, soft duplicates."""

from tests.helpers import login_client, provision_tenant, tenant_headers


def test_register_search_update_and_import(client, owner_db, make_owner_user, make_tenant):
    base = provision_tenant(
        owner_db, make_owner_user, make_tenant, slug="crm-a", admin_email="crm-a@example.com"
    )
    tid = str(base["tenant"].id)
    admin = login_client(client, email=base["admin"].email)
    h = tenant_headers(tid)

    created = admin.post(
        f"/api/v1/tenants/{tid}/patients",
        headers=h,
        json={
            "display_name": "Synthetic Ada",
            "phone": "+911111111111",
            "email": "ada@example.com",
            "date_of_birth": "1990-01-15",
            "emergency_contact_name": "Bob Ada",
            "emergency_contact_phone": "+912222222222",
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["email"] == "ada@example.com"
    assert body["date_of_birth"] == "1990-01-15"
    pid = body["id"]

    listed = admin.get(f"/api/v1/tenants/{tid}/patients?q=ada", headers=h)
    assert listed.status_code == 200
    assert any(p["id"] == pid for p in listed.json())

    patched = admin.patch(
        f"/api/v1/tenants/{tid}/patients/{pid}",
        headers=h,
        json={"phone": "+913333333333", "is_active": True},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["phone"] == "+913333333333"

    # Soft duplicate signal on matching email
    dup = admin.post(
        f"/api/v1/tenants/{tid}/patients",
        headers=h,
        json={"display_name": "Synthetic Ada Twin", "email": "ada@example.com"},
    )
    assert dup.status_code == 200
    assert pid in dup.json()["potential_duplicates"]

    imported = admin.post(
        f"/api/v1/tenants/{tid}/patients/import",
        headers=h,
        json={
            "rows": [
                {"display_name": "Import One", "phone": "+914444444444"},
                {"display_name": "Import Dup", "email": "ada@example.com"},
                {"display_name": "Bad Email", "email": "not-an-email"},
            ]
        },
    )
    assert imported.status_code == 200, imported.text
    summary = imported.json()
    assert summary["created"] == 1
    assert summary["skipped"] == 1
    assert summary["errors"] == 1


def test_patient_cross_tenant_404(client, owner_db, make_owner_user, make_tenant):
    a = provision_tenant(
        owner_db, make_owner_user, make_tenant, slug="crm-x", admin_email="crm-x@example.com"
    )
    b = provision_tenant(
        owner_db, make_owner_user, make_tenant, slug="crm-y", admin_email="crm-y@example.com"
    )
    ca = login_client(client, email=a["admin"].email)
    ha = tenant_headers(str(a["tenant"].id))
    pb = (
        login_client(client, email=b["admin"].email)
        .post(
            f"/api/v1/tenants/{b['tenant'].id}/patients",
            headers=tenant_headers(str(b["tenant"].id)),
            json={"display_name": "Other Tenant Patient"},
        )
        .json()
    )
    r = ca.get(f"/api/v1/tenants/{a['tenant'].id}/patients/{pb['id']}", headers=ha)
    assert r.status_code == 404
