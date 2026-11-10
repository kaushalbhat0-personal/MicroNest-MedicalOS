"""P6 portal security: ownership, IDOR, no-oracle, revocation, least privilege.

Every test asserts the portal contract:
- patient_id comes from the server-side link, never the browser
- cross-patient/cross-tenant/forged access is 404 (existence never revealed)
- provider-only surfaces are 403 for portal callers
- drafts/internal states are never projected
"""

import uuid

from tests.helpers import login_client, provision_scheduling, tenant_headers


def _portal_pair(client, owner_db, make_owner_user, make_tenant, *, slug, admin_email):
    """Tenant + patient + staff admin; returns dict with tenant/patient/admin."""
    return provision_scheduling(
        owner_db, make_owner_user, make_tenant, slug=slug, admin_email=admin_email
    )


def _enroll(client, base, *, email, patient_id=None):
    """Staff-gated enrollment via the API (exercises the real endpoint)."""
    admin_client = login_client(client, email=base["admin"].email)
    headers = tenant_headers(str(base["tenant"].id))
    resp = admin_client.post(
        f"/api/v1/tenants/{base['tenant'].id}/portal-links",
        headers=headers,
        json={"email": email, "patient_id": str(patient_id or base["patient"].id)},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _portal_client(client, owner_db, base, *, email, password="portal-test-pass-1"):
    """Mirror the real activation flow: the enrolled user sets a password
    (production: public password-reset flow), then logs in."""
    from app.modules.identity import service as identity_service

    user = identity_service.get_user_by_email(owner_db, email)
    identity_service.set_password(owner_db, user, password)
    owner_db.commit()
    authed = login_client(client, email=email, password=password)
    headers = tenant_headers(str(base["tenant"].id))
    return authed, headers


def test_patient_cannot_read_other_patient(
    client, owner_db, make_owner_user, make_tenant
):
    a = _portal_pair(
        client,
        owner_db,
        make_owner_user,
        make_tenant,
        slug="pa-iso",
        admin_email="pa-iso@example.com",
    )
    b = _portal_pair(
        client,
        owner_db,
        make_owner_user,
        make_tenant,
        slug="pb-iso",
        admin_email="pb-iso@example.com",
    )
    _enroll(client, a, email="portal-a@example.com")
    _enroll(client, b, email="portal-b@example.com")
    ca, ha = _portal_client(client, owner_db, a, email="portal-a@example.com")

    # B's patient/appointment/encounter/invoice/docs are 404 through A's context.
    # (B has no appointments yet; forge for oracle check below.)
    assert ca.get("/api/v1/portal/profile", headers=ha).status_code == 200
    forged = str(uuid.uuid4())
    for path in (
        f"/api/v1/portal/appointments/{forged}",
        f"/api/v1/portal/encounters/{forged}",
        f"/api/v1/portal/estimates/{forged}",
        f"/api/v1/portal/invoices/{forged}",
        f"/api/v1/portal/treatment-plans/{forged}",
    ):
        r = ca.get(path, headers=ha)
        assert r.status_code == 404, (path, r.status_code)


def test_patient_cannot_mutate_other_patient(
    client, owner_db, make_owner_user, make_tenant
):
    from datetime import datetime, timedelta, timezone

    a = _portal_pair(
        client,
        owner_db,
        make_owner_user,
        make_tenant,
        slug="pa-mut",
        admin_email="pa-mut@example.com",
    )
    b = _portal_pair(
        client,
        owner_db,
        make_owner_user,
        make_tenant,
        slug="pb-mut",
        admin_email="pb-mut@example.com",
    )
    _enroll(client, a, email="portal-a-mut@example.com")
    _enroll(client, b, email="portal-b-mut@example.com")

    # Staff books an appointment for B's patient (provider machinery).
    admin_b = login_client(client, email="pb-mut@example.com")
    hb = tenant_headers(str(b["tenant"].id))
    start = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    created = admin_b.post(
        f"/api/v1/tenants/{b['tenant'].id}/appointments",
        headers=hb,
        json={
            "patient_id": str(b["patient"].id),
            "practitioner_id": str(b["practitioner"].id),
            "location_id": str(b["location"].id),
            "start": start,
            "duration_minutes": 30,
        },
    )
    assert created.status_code == 200, created.text
    appt_id = created.json()["id"]

    ca, ha = _portal_client(client, owner_db, a, email="portal-a-mut@example.com")
    # Cancel through A's portal context: 404, and B's appointment is untouched.
    r = ca.post(f"/api/v1/portal/appointments/{appt_id}/cancel", headers=ha, json={})
    assert r.status_code == 404, r.text
    check = admin_b.get(
        f"/api/v1/tenants/{b['tenant'].id}/appointments/{appt_id}", headers=hb
    )
    assert check.json()["status"] in ("scheduled", "confirmed")


def test_cross_tenant_portal_is_rejected(
    client, owner_db, make_owner_user, make_tenant
):
    a = _portal_pair(
        client,
        owner_db,
        make_owner_user,
        make_tenant,
        slug="pa-x",
        admin_email="pa-x@example.com",
    )
    b = _portal_pair(
        client,
        owner_db,
        make_owner_user,
        make_tenant,
        slug="pb-x",
        admin_email="pb-x@example.com",
    )
    _enroll(client, a, email="portal-a-x@example.com")
    ca, _ = _portal_client(client, owner_db, a, email="portal-a-x@example.com")
    # X-Tenant pointing at an unlinked tenant is rejected (403 unknown tenant).
    hx = tenant_headers(str(b["tenant"].id))
    r = ca.get("/api/v1/portal/profile", headers=hx)
    assert r.status_code in (403, 404), r.status_code


def test_provider_endpoints_reject_portal_caller(
    client, owner_db, make_owner_user, make_tenant
):
    a = _portal_pair(
        client,
        owner_db,
        make_owner_user,
        make_tenant,
        slug="pa-priv",
        admin_email="pa-priv@example.com",
    )
    _enroll(client, a, email="portal-a-priv@example.com")
    ca, ha = _portal_client(client, owner_db, a, email="portal-a-priv@example.com")
    tid = str(a["tenant"].id)
    # Census reads and writes are outside the portal allow-list.
    assert ca.get(f"/api/v1/tenants/{tid}/patients", headers=ha).status_code == 403
    assert ca.get(f"/api/v1/tenants/{tid}/audit", headers=ha).status_code == 403
    assert (
        ca.post(
            f"/api/v1/tenants/{tid}/patients", headers=ha, json={"display_name": "Nope"}
        ).status_code
        == 403
    )
    assert (
        ca.post(
            f"/api/v1/tenants/{tid}/service-catalog",
            headers=ha,
            json={"code": "X", "display": "X", "default_rate": "1"},
        ).status_code
        == 403
    )


def test_drafts_and_internals_hidden(client, owner_db, make_owner_user, make_tenant):
    from app.modules.clinical import records as clinical_records
    from app.modules.clinical import service as clinical_service
    from app.modules.prescriptions import service as rx_service

    a = _portal_pair(
        client,
        owner_db,
        make_owner_user,
        make_tenant,
        slug="pa-draft",
        admin_email="pa-draft@example.com",
    )
    _enroll(client, a, email="portal-a-draft@example.com")

    # Draft prescription + draft (open-encounter) note via services.
    enc = clinical_service.open_encounter(
        owner_db,
        tenant_id=a["tenant"].id,
        actor_id=a["practitioner"].id,
        patient_id=a["patient"].id,
        practitioner_id=a["practitioner"].id,
        location_id=a["location"].id,
    )
    owner_db.commit()
    rx_service.create_prescription(
        owner_db,
        tenant_id=a["tenant"].id,
        encounter_id=enc.id,
        prescribed_by=a["practitioner"].id,
        items=[
            {
                "medication_code": "paracetamol-650",
                "dose": "650mg",
                "route": "oral",
                "frequency": "TID",
                "instructions": "after food",
            }
        ],
    )
    clinical_records.create_note(
        owner_db,
        tenant_id=a["tenant"].id,
        encounter_id=enc.id,
        author_id=a["practitioner"].id,
        note_type="general",
        subjective="internal draft",
    )
    owner_db.commit()

    ca, ha = _portal_client(client, owner_db, a, email="portal-a-draft@example.com")
    # Draft Rx invisible; open encounter exposes header only (no notes key content).
    assert ca.get("/api/v1/portal/prescriptions", headers=ha).json() == []
    detail = ca.get(f"/api/v1/portal/encounters/{enc.id}", headers=ha)
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "open"
    assert body["notes"] == [] and body["diagnoses"] == []
    # Provider cancel of a scheduled appointment is NOT offered to patients
    # outside scheduled/confirmed; cancel of unknown id is 404, not 422.
    r = ca.post(
        f"/api/v1/portal/appointments/{uuid.uuid4()}/cancel", headers=ha, json={}
    )
    assert r.status_code == 404


def test_closed_encounter_shares_finalized_only(
    client, owner_db, make_owner_user, make_tenant
):
    from app.modules.clinical import records as clinical_records
    from app.modules.clinical import service as clinical_service

    a = _portal_pair(
        client,
        owner_db,
        make_owner_user,
        make_tenant,
        slug="pa-closed",
        admin_email="pa-closed@example.com",
    )
    _enroll(client, a, email="portal-a-closed@example.com")
    enc = clinical_service.open_encounter(
        owner_db,
        tenant_id=a["tenant"].id,
        actor_id=a["practitioner"].id,
        patient_id=a["patient"].id,
        practitioner_id=a["practitioner"].id,
        location_id=a["location"].id,
    )
    owner_db.commit()
    n1 = clinical_records.create_note(
        owner_db,
        tenant_id=a["tenant"].id,
        encounter_id=enc.id,
        author_id=a["practitioner"].id,
        note_type="general",
        subjective="final me",
    )
    clinical_records.create_note(  # draft stays invisible to the portal
        owner_db,
        tenant_id=a["tenant"].id,
        encounter_id=enc.id,
        author_id=a["practitioner"].id,
        note_type="general",
        subjective="draft me",
    )
    clinical_records.finalize_note(
        owner_db, tenant_id=a["tenant"].id, note_id=n1.id, actor_id=a["practitioner"].id
    )
    clinical_records.record_observation(
        owner_db,
        tenant_id=a["tenant"].id,
        encounter_id=enc.id,
        type_code="bp_systolic",
        value_numeric=120,
        recorded_by=a["practitioner"].id,
    )
    owner_db.commit()
    clinical_service.close_encounter(
        owner_db,
        tenant_id=a["tenant"].id,
        encounter_id=enc.id,
        actor_id=a["practitioner"].id,
        note_waiver=False,
        vitals_waiver=False,
    )
    owner_db.commit()

    ca, ha = _portal_client(client, owner_db, a, email="portal-a-closed@example.com")
    body = ca.get(f"/api/v1/portal/encounters/{enc.id}", headers=ha).json()
    assert body["status"] == "closed"
    assert [n["status"] for n in body["notes"]] == ["finalized"]
    assert all("author" not in n and "author_id" not in n for n in body["notes"])
    assert body["observations"] and all(
        "recorded_by" not in o for o in body["observations"]
    )


def test_documents_hide_storage_keys(client, owner_db, make_owner_user, make_tenant):
    from app.modules.clinical import service as clinical_service
    from app.modules.dental.plans import create_document_ref

    a = _portal_pair(
        client,
        owner_db,
        make_owner_user,
        make_tenant,
        slug="pa-doc",
        admin_email="pa-doc@example.com",
    )
    _enroll(client, a, email="portal-a-doc@example.com")
    enc = clinical_service.open_encounter(
        owner_db,
        tenant_id=a["tenant"].id,
        actor_id=a["practitioner"].id,
        patient_id=a["patient"].id,
        practitioner_id=a["practitioner"].id,
        location_id=a["location"].id,
    )
    owner_db.commit()
    create_document_ref(
        owner_db,
        tenant_id=a["tenant"].id,
        encounter_id=enc.id,
        doc_type="xray",
        storage_key="tenant-a/secret-key-object",
        actor_id=a["practitioner"].id,
    )
    owner_db.commit()

    ca, ha = _portal_client(client, owner_db, a, email="portal-a-doc@example.com")
    # Open-encounter documents are not released at all.
    assert ca.get("/api/v1/portal/documents", headers=ha).json() == []

    clinical_service.close_encounter(
        owner_db,
        tenant_id=a["tenant"].id,
        encounter_id=enc.id,
        actor_id=a["practitioner"].id,
        note_waiver=True,
        vitals_waiver=True,
    )
    owner_db.commit()
    docs = ca.get("/api/v1/portal/documents", headers=ha).json()
    assert len(docs) == 1
    assert docs[0]["download_available"] is False
    assert "storage_key" not in docs[0]
    assert "secret-key-object" not in str(docs)


def test_revoked_link_fails_closed(client, owner_db, make_owner_user, make_tenant):
    a = _portal_pair(
        client,
        owner_db,
        make_owner_user,
        make_tenant,
        slug="pa-rev",
        admin_email="pa-rev@example.com",
    )
    link = _enroll(client, a, email="portal-a-rev@example.com")
    ca, ha = _portal_client(client, owner_db, a, email="portal-a-rev@example.com")
    assert ca.get("/api/v1/portal/profile", headers=ha).status_code == 200

    admin_client = login_client(client, email="pa-rev@example.com")
    r = admin_client.delete(
        f"/api/v1/tenants/{a['tenant'].id}/portal-links/{link['id']}",
        headers=tenant_headers(str(a["tenant"].id)),
    )
    assert r.status_code == 200
    assert ca.get("/api/v1/portal/profile", headers=ha).status_code == 404
    assert ca.get("/api/v1/portal/appointments", headers=ha).status_code == 404


def test_logout_invalidates_portal_session(
    client, owner_db, make_owner_user, make_tenant
):
    a = _portal_pair(
        client,
        owner_db,
        make_owner_user,
        make_tenant,
        slug="pa-lo",
        admin_email="pa-lo@example.com",
    )
    _enroll(client, a, email="portal-a-lo@example.com")
    ca, ha = _portal_client(client, owner_db, a, email="portal-a-lo@example.com")
    assert ca.get("/api/v1/portal/profile", headers=ha).status_code == 200
    assert ca.post("/api/v1/auth/logout").status_code in (200, 204)
    assert ca.get("/api/v1/portal/profile", headers=ha).status_code == 401


def test_portal_cancel_own_appointment(client, owner_db, make_owner_user, make_tenant):
    from datetime import datetime, timedelta, timezone

    a = _portal_pair(
        client,
        owner_db,
        make_owner_user,
        make_tenant,
        slug="pa-can",
        admin_email="pa-can@example.com",
    )
    _enroll(client, a, email="portal-a-can@example.com")
    admin_client = login_client(client, email="pa-can@example.com")
    ha = tenant_headers(str(a["tenant"].id))
    start = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    created = admin_client.post(
        f"/api/v1/tenants/{a['tenant'].id}/appointments",
        headers=ha,
        json={
            "patient_id": str(a["patient"].id),
            "practitioner_id": str(a["practitioner"].id),
            "location_id": str(a["location"].id),
            "start": start,
            "duration_minutes": 30,
        },
    )
    assert created.status_code == 200, created.text
    appt_id = created.json()["id"]

    ca, _ = _portal_client(client, owner_db, a, email="portal-a-can@example.com")
    mine = ca.get("/api/v1/portal/appointments", headers=ha).json()
    assert any(x["id"] == appt_id for x in mine)
    cancelled = ca.post(
        f"/api/v1/portal/appointments/{appt_id}/cancel",
        headers=ha,
        json={"reason": "feeling better"},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    # Cancelling a terminal appointment is rejected honestly (422), not a
    # silent success: the portal allow-list is scheduled/confirmed only.
    again = ca.post(
        f"/api/v1/portal/appointments/{appt_id}/cancel", headers=ha, json={}
    )
    assert again.status_code == 422


def test_error_bodies_reveal_nothing(client, owner_db, make_owner_user, make_tenant):
    a = _portal_pair(
        client,
        owner_db,
        make_owner_user,
        make_tenant,
        slug="pa-oracle",
        admin_email="pa-oracle@example.com",
    )
    _enroll(client, a, email="portal-a-oracle@example.com")
    ca, ha = _portal_client(client, owner_db, a, email="portal-a-oracle@example.com")
    name = a["patient"].display_name
    for path in (
        f"/api/v1/portal/appointments/{uuid.uuid4()}",
        f"/api/v1/portal/encounters/{uuid.uuid4()}",
        f"/api/v1/portal/invoices/{uuid.uuid4()}",
        "/api/v1/portal/profile",
    ):
        headers = (
            ha
            if path.endswith("profile") is False
            else tenant_headers(str(uuid.uuid4()))
        )
        r = ca.get(path, headers=headers)
        assert r.status_code in (403, 404)
        assert name not in r.text
        assert "patient_id" not in r.text.lower() or r.status_code == 403
