"""P8 discovery slice: two-tenant pilot readiness (synthetic data only).

Proves, through the API boundary on the isolated TEST database:
- Tenant A (dental pilot) and Tenant B (eye pilot) are independent.
- Patients, appointments, clinical records, billing, portal links, audit
  never cross tenants (404 oracle, 403 on selector abuse).
- Location scope, role bundles, and dual-membership tenant switching hold.

No schema changes. No production/preview database access. No real identities.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tests.helpers import login_client, provision_clinical, tenant_headers


def _two_pilots(client, owner_db, make_owner_user, make_tenant):  # type: ignore[no-untyped-def]
    a = provision_clinical(
        owner_db,
        make_owner_user,
        make_tenant,
        slug="p8-dental-a",
        admin_email="p8-dental-admin@example.com",
        doctor_email="p8-dental-doc@example.com",
        practitioner_name="P8 Dental Doctor",
        patient_name="P8 Dental Patient",
    )
    b = provision_clinical(
        owner_db,
        make_owner_user,
        make_tenant,
        slug="p8-eye-b",
        admin_email="p8-eye-admin@example.com",
        doctor_email="p8-eye-doc@example.com",
        practitioner_name="P8 Eye Doctor",
        patient_name="P8 Eye Patient",
    )
    return a, b


def _appt_body(pilot):  # type: ignore[no-untyped-def]
    start = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    return {
        "patient_id": str(pilot["patient"].id),
        "practitioner_id": str(pilot["practitioner"].id),
        "location_id": str(pilot["location"].id),
        "start": start,
        "duration_minutes": 30,
    }


def test_tenants_and_locations_independent(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    a, b = _two_pilots(client, owner_db, make_owner_user, make_tenant)
    assert a["tenant"].id != b["tenant"].id
    assert a["tenant"].slug != b["tenant"].slug
    assert a["location"].tenant_id == a["tenant"].id
    assert b["location"].tenant_id == b["tenant"].id
    ca = login_client(client, email="p8-dental-admin@example.com")
    ha = tenant_headers(str(a["tenant"].id))
    # Own tenant + locations read back; foreign location rejected on scoped update.
    assert ca.get(f"/api/v1/tenants/{a['tenant'].id}", headers=ha).status_code == 200
    locs = ca.get(f"/api/v1/tenants/{a['tenant'].id}/locations", headers=ha)
    assert locs.status_code == 200
    assert all(str(a["tenant"].id) != str(b["tenant"].id) for _ in [0])
    assert {str(a["location"].id)} <= {loc["id"] for loc in locs.json()}
    members = ca.get(f"/api/v1/tenants/{a['tenant'].id}/memberships", headers=ha).json()
    mid = members[0]["id"]
    r = ca.patch(
        f"/api/v1/tenants/{a['tenant'].id}/memberships/{mid}",
        headers=ha,
        json={"location_ids": [str(b["location"].id)]},
    )
    assert r.status_code in (403, 404)


def test_staff_membership_and_role_bundles(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from app.modules.tenancy import service as tenancy_service

    a, b = _two_pilots(client, owner_db, make_owner_user, make_tenant)
    recep = make_owner_user(email="p8-recep@example.com")
    tenancy_service.create_membership(
        owner_db,
        user=recep,
        tenant=a["tenant"],
        role=tenancy_service.get_seed_role(owner_db, "receptionist"),
        location_ids=[a["location"].id],
    )
    owner_db.commit()
    rc = login_client(client, email="p8-recep@example.com")
    ha = tenant_headers(str(a["tenant"].id))
    # Receptionist books in own tenant but cannot touch tenant B.
    created = rc.post(
        f"/api/v1/tenants/{a['tenant'].id}/appointments",
        headers=ha,
        json=_appt_body(a),
    )
    assert created.status_code == 200, created.text
    hb = tenant_headers(str(b["tenant"].id))
    assert rc.get(f"/api/v1/tenants/{b['tenant'].id}", headers=hb).status_code == 403
    assert rc.get(
        f"/api/v1/tenants/{b['tenant'].id}/patients", headers=hb
    ).status_code in (403, 404)


def test_patient_appointment_clinical_isolation(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    a, b = _two_pilots(client, owner_db, make_owner_user, make_tenant)
    da = login_client(client, email="p8-dental-doc@example.com")
    db_login = login_client(client, email="p8-eye-doc@example.com")
    admin_a = login_client(client, email="p8-dental-admin@example.com")
    ha = tenant_headers(str(a["tenant"].id))
    hb = tenant_headers(str(b["tenant"].id))
    # Cross-patient encounter creation fails closed.
    bad = da.post(
        f"/api/v1/tenants/{a['tenant'].id}/encounters",
        json={
            "patient_id": str(b["patient"].id),
            "practitioner_id": str(a["practitioner"].id),
            "location_id": str(a["location"].id),
        },
        headers=ha,
    )
    assert bad.status_code == 404
    # Own encounter + note succeed; foreign reads are 404.
    enc = da.post(
        f"/api/v1/tenants/{a['tenant'].id}/encounters",
        json={
            "patient_id": str(a["patient"].id),
            "practitioner_id": str(a["practitioner"].id),
            "location_id": str(a["location"].id),
        },
        headers=ha,
    )
    assert enc.status_code == 200, enc.text
    eid = enc.json()["id"]
    note = da.post(
        f"/api/v1/tenants/{a['tenant'].id}/encounters/{eid}/clinical-notes",
        json={"assessment": "synthetic assessment"},
        headers=ha,
    )
    assert note.status_code == 200, note.text
    assert (
        db_login.get(
            f"/api/v1/tenants/{b['tenant'].id}/encounters/{eid}", headers=hb
        ).status_code
        == 404
    )
    # Appointment isolation both directions (admin holds appointment.create;
    # doctor role intentionally lacks it — least privilege by design).
    appt = admin_a.post(
        f"/api/v1/tenants/{a['tenant'].id}/appointments",
        headers=ha,
        json=_appt_body(a),
    )
    assert appt.status_code == 200, appt.text
    assert (
        db_login.get(
            f"/api/v1/tenants/{b['tenant'].id}/appointments/{appt.json()['id']}",
            headers=hb,
        ).status_code
        == 404
    )


def test_billing_isolation(client, owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    a, b = _two_pilots(client, owner_db, make_owner_user, make_tenant)
    ca = login_client(client, email="p8-dental-admin@example.com")
    cb = login_client(client, email="p8-eye-admin@example.com")
    ha = tenant_headers(str(a["tenant"].id))
    hb = tenant_headers(str(b["tenant"].id))
    body = {
        "patient_id": str(a["patient"].id),
        "location_id": str(a["location"].id),
        "items": [
            {
                "description": "Synthetic filling",
                "quantity": "1",
                "unit_rate": "500.00",
            }
        ],
    }
    inv = ca.post(f"/api/v1/tenants/{a['tenant'].id}/invoices", json=body, headers=ha)
    assert inv.status_code == 200, inv.text
    iid = inv.json()["id"]
    assert (
        ca.get(
            f"/api/v1/tenants/{a['tenant'].id}/invoices/{iid}", headers=ha
        ).status_code
        == 200
    )
    assert (
        cb.get(
            f"/api/v1/tenants/{b['tenant'].id}/invoices/{iid}", headers=hb
        ).status_code
        == 404
    )
    listed = cb.get(f"/api/v1/tenants/{b['tenant'].id}/invoices", headers=hb)
    assert listed.status_code == 200
    assert all(row["id"] != iid for row in listed.json()["items"])


def _enroll(client, base, *, email):  # type: ignore[no-untyped-def]
    admin_client = login_client(client, email=base["admin"].email)
    headers = tenant_headers(str(base["tenant"].id))
    resp = admin_client.post(
        f"/api/v1/tenants/{base['tenant'].id}/portal-links",
        headers=headers,
        json={"email": email, "patient_id": str(base["patient"].id)},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _portal_login(client, owner_db, *, email, password="p8-portal-pass-1"):  # type: ignore[no-untyped-def]
    from app.modules.identity import service as identity_service

    user = identity_service.get_user_by_email(owner_db, email)
    identity_service.set_password(owner_db, user, password)
    owner_db.commit()
    return login_client(client, email=email, password=password)


def test_portal_enrollment_and_cross_tenant_isolation(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    import uuid as _uuid

    a, b = _two_pilots(client, owner_db, make_owner_user, make_tenant)
    _enroll(client, a, email="p8-portal-dental@example.com")
    _enroll(client, b, email="p8-portal-eye@example.com")
    pa = _portal_login(client, owner_db, email="p8-portal-dental@example.com")
    ha = tenant_headers(str(a["tenant"].id))
    assert pa.get("/api/v1/portal/profile", headers=ha).status_code == 200
    # Cross-tenant header rejected; forged ids are 404.
    hx = tenant_headers(str(b["tenant"].id))
    assert pa.get("/api/v1/portal/profile", headers=hx).status_code in (403, 404)
    forged = str(_uuid.uuid4())
    for path in (
        f"/api/v1/portal/appointments/{forged}",
        f"/api/v1/portal/encounters/{forged}",
        f"/api/v1/portal/invoices/{forged}",
        f"/api/v1/portal/treatment-plans/{forged}",
    ):
        assert pa.get(path, headers=ha).status_code == 404


def test_audit_isolation(client, owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    a, b = _two_pilots(client, owner_db, make_owner_user, make_tenant)
    ca = login_client(client, email="p8-dental-admin@example.com")
    ha = tenant_headers(str(a["tenant"].id))
    hb = tenant_headers(str(b["tenant"].id))
    own = ca.get(f"/api/v1/tenants/{a['tenant'].id}/audit", headers=ha)
    assert own.status_code == 200
    # Foreign tenant id under own selector, and own path under foreign selector.
    assert (
        ca.get(f"/api/v1/tenants/{b['tenant'].id}/audit", headers=ha).status_code == 404
    )
    assert ca.get(
        f"/api/v1/tenants/{a['tenant'].id}/audit", headers=hb
    ).status_code in (
        403,
        404,
    )


def test_dual_membership_tenant_switching(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from app.modules.identity import service as identity_service
    from app.modules.tenancy import service as tenancy_service

    ta = make_tenant(slug="p8-dual-a")
    tb = make_tenant(slug="p8-dual-b")
    user = identity_service.create_user(
        owner_db,
        email="p8-dual@example.com",
        display_name="P8 Dual",
        password="password-12345-abc",
    )
    role = tenancy_service.get_seed_role(owner_db, "tenant_admin")
    tenancy_service.create_membership(owner_db, user=user, tenant=ta, role=role)
    tenancy_service.create_membership(owner_db, user=user, tenant=tb, role=role)
    owner_db.commit()
    c = login_client(client, email="p8-dual@example.com")
    assert c.get(f"/api/v1/tenants/{ta.id}").status_code == 403
    assert (
        c.get(
            f"/api/v1/tenants/{ta.id}", headers=tenant_headers(str(ta.id))
        ).status_code
        == 200
    )
    assert (
        c.get(
            f"/api/v1/tenants/{tb.id}", headers=tenant_headers(str(tb.id))
        ).status_code
        == 200
    )


def test_tenant_identity_independent_no_shared_branding_surface(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    """Negative branding check for this slice: tenant names are independent and
    no cross-tenant branding field exists. Full white-label lands in P8.2."""
    a, b = _two_pilots(client, owner_db, make_owner_user, make_tenant)
    assert a["tenant"].name != b["tenant"].name or a["tenant"].slug != b["tenant"].slug
    ca = login_client(client, email="p8-dental-admin@example.com")
    ha = tenant_headers(str(a["tenant"].id))
    body = ca.get(f"/api/v1/tenants/{a['tenant'].id}", headers=ha).json()
    assert str(b["tenant"].id) not in str(body)
    assert b["tenant"].slug not in str(body)
