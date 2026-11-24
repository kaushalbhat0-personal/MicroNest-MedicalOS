"""P3.6 synthetic-data security verification.

Two-tenant fixtures (A/B) with unmistakably fictional identities.
Exercises document storage_key binding, dental consent hard-gate, and
cross-tenant / IDOR controls against the real local test DB + storage
adapter (not production S3 isolation).
"""

from __future__ import annotations

import time
import uuid

import pytest
from sqlalchemy import text

from app.modules.dental import models as DM
from app.modules.dental import plans as dplans
from app.platform.adapters.s3_storage import build_storage_adapter
from app.platform.config import get_settings
from app.platform.errors import ForbiddenError
from tests.helpers import login_client, provision_clinical, tenant_headers


# --- Synthetic fixture names (never real PHI) ---
_SYN_A = {
    "slug": "p36-syn-tenant-a",
    "admin_email": "owner.a.p36.synthetic@example.com",
    "doctor_email": "dentist.a.p36.synthetic@example.com",
    "patient_name": "Synthetic Patient A1",
}
_SYN_B = {
    "slug": "p36-syn-tenant-b",
    "admin_email": "owner.b.p36.synthetic@example.com",
    "doctor_email": "dentist.b.p36.synthetic@example.com",
    "patient_name": "Synthetic Patient B1",
}


def _bundle(client, owner_db, make_owner_user, make_tenant, syn: dict):  # type: ignore[no-untyped-def]
    b = provision_clinical(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=syn["slug"],
        admin_email=syn["admin_email"],
        doctor_email=syn.get("doctor_email"),
        patient_name=syn["patient_name"],
    )
    # Extra synthetic patient in-tenant for cross-patient probes.
    from app.modules.patients import service as patients_service
    from app.modules.tenancy import service as tenancy_service

    p2 = patients_service.register_patient(
        owner_db,
        tenant_id=b["tenant"].id,
        display_name=syn["patient_name"].replace("1", "2"),
    )
    # Receptionist membership (staff role — no dental_record / dental_read).
    receptionist = make_owner_user(
        email=syn["admin_email"].replace("owner", "reception")
    )
    tenancy_service.create_membership(
        owner_db,
        user=receptionist,
        tenant=b["tenant"],
        role=tenancy_service.get_seed_role(owner_db, "staff"),
    )
    owner_db.commit()
    doctor = login_client(client, email=b["doctor"].email)
    h = tenant_headers(b["tenant"].id)
    b["patient2"] = p2
    b["receptionist"] = receptionist
    return b, doctor, h


def _open_encounter(c, tid, b, *, patient=None, location=None):  # type: ignore[no-untyped-def]
    r = c.post(
        f"/api/v1/tenants/{tid}/encounters",
        json={
            "patient_id": str((patient or b["patient"]).id),
            "practitioner_id": str(b["practitioner"].id),
            "location_id": str((location or b["location"]).id),
        },
        headers=tenant_headers(tid),
    )
    assert r.status_code == 200, r.text
    return r.json()


def _create_doc(c, tid, encounter_id, h, **kw):  # type: ignore[no-untyped-def]
    body = {
        "doc_type": "xray",
        "content_type": "image/png",
        "sha256": "deadbeef",
    }
    body.update(kw)
    r = c.post(
        f"/api/v1/tenants/{tid}/encounters/{encounter_id}/documents",
        json=body,
        headers=h,
    )
    return r


def _access(c, tid, document_id, h):  # type: ignore[no-untyped-def]
    return c.post(
        f"/api/v1/tenants/{tid}/documents/{document_id}/access",
        json={},
        headers=h,
    )


def _grant_procedure_consent(c, tid, record_id, h, *, name="Synthetic Consenter"):  # type: ignore[no-untyped-def]
    consent = c.post(
        f"/api/v1/tenants/{tid}/consents",
        json={
            "procedure_record_id": record_id,
            "consenter_name": name,
            "consenter_relation": "self",
        },
        headers=h,
    )
    assert consent.status_code == 200, consent.text
    decide = c.post(
        f"/api/v1/tenants/{tid}/consents/{consent.json()['id']}/decide",
        json={"decision": "granted"},
        headers=h,
    )
    assert decide.status_code == 200, decide.text
    return consent.json()["id"]


# ---------------------------------------------------------------------------
# Document security
# ---------------------------------------------------------------------------


def test_p36_authorized_retrieval_uses_server_key(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    a, doc_a, ha = _bundle(client, owner_db, make_owner_user, make_tenant, _SYN_A)
    tid = a["tenant"].id
    enc = _open_encounter(doc_a, tid, a)
    created = _create_doc(
        doc_a, tid, enc["id"], ha, storage_key="client-wants/evil.png"
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["storage_key"].startswith(f"tenants/{tid}/encounters/{enc['id']}/documents/")
    assert "evil" not in body["storage_key"]
    access = _access(doc_a, tid, body["id"], ha)
    assert access.status_code == 200, access.text
    assert "storage_key" not in access.json()
    assert body["storage_key"] not in access.text


def test_p36_client_storage_key_cannot_select_object(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    a, doc_a, ha = _bundle(client, owner_db, make_owner_user, make_tenant, _SYN_A)
    b, _doc_b, _hb = _bundle(client, owner_db, make_owner_user, make_tenant, _SYN_B)
    tid = a["tenant"].id
    enc = _open_encounter(doc_a, tid, a)
    # Attempt to point at tenant B's object path — must be ignored.
    foreign = f"tenants/{b['tenant'].id}/encounters/{uuid.uuid4()}/documents/{uuid.uuid4()}"
    created = _create_doc(doc_a, tid, enc["id"], ha, storage_key=foreign)
    assert created.status_code == 200, created.text
    key = created.json()["storage_key"]
    assert str(b["tenant"].id) not in key
    assert key.startswith(f"tenants/{tid}/")


@pytest.mark.parametrize(
    "bad_key",
    [
        "../etc/passwd",
        "/absolute/path.png",
        "tenants\\escape\\key",
        "x\0y",
    ],
)
def test_p36_path_traversal_storage_key_rejected(
    client, owner_db, make_owner_user, make_tenant, bad_key
) -> None:  # type: ignore[no-untyped-def]
    a, doc_a, ha = _bundle(
        client,
        owner_db,
        make_owner_user,
        make_tenant,
        {**_SYN_A, "slug": f"p36-trav-{uuid.uuid4().hex[:6]}"},
    )
    tid = a["tenant"].id
    enc = _open_encounter(doc_a, tid, a)
    r = _create_doc(doc_a, tid, enc["id"], ha, storage_key=bad_key)
    assert r.status_code == 422, r.text


def test_p36_cross_tenant_document_id_is_404(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    a, doc_a, ha = _bundle(client, owner_db, make_owner_user, make_tenant, _SYN_A)
    b, doc_b, hb = _bundle(client, owner_db, make_owner_user, make_tenant, _SYN_B)
    enc = _open_encounter(doc_a, a["tenant"].id, a)
    ref = _create_doc(doc_a, a["tenant"].id, enc["id"], ha).json()
    assert _access(doc_b, b["tenant"].id, ref["id"], hb).status_code == 404
    assert _access(doc_b, a["tenant"].id, ref["id"], hb).status_code == 404


def test_p36_cross_patient_same_tenant_follows_provider_read_model(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    """Provider dental_read is tenant+location scoped (existing model)."""
    a, doc_a, ha = _bundle(client, owner_db, make_owner_user, make_tenant, _SYN_A)
    tid = a["tenant"].id
    enc2 = _open_encounter(doc_a, tid, a, patient=a["patient2"])
    ref = _create_doc(doc_a, tid, enc2["id"], ha).json()
    assert _access(doc_a, tid, ref["id"], ha).status_code == 200


def test_p36_cross_encounter_list_scoped(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    a, doc_a, ha = _bundle(client, owner_db, make_owner_user, make_tenant, _SYN_A)
    tid = a["tenant"].id
    e1 = _open_encounter(doc_a, tid, a)
    e2 = _open_encounter(doc_a, tid, a, patient=a["patient2"])
    _create_doc(doc_a, tid, e1["id"], ha)
    listed = doc_a.get(
        f"/api/v1/tenants/{tid}/encounters/{e2['id']}/documents", headers=ha
    )
    assert listed.status_code == 200
    assert listed.json() == []


def test_p36_unauthorized_upload_is_403(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    a, doc_a, ha = _bundle(client, owner_db, make_owner_user, make_tenant, _SYN_A)
    tid = a["tenant"].id
    enc = _open_encounter(doc_a, tid, a)
    staff = login_client(client, email=a["receptionist"].email)
    r = _create_doc(staff, tid, enc["id"], ha)
    assert r.status_code == 403


def test_p36_document_delete_endpoint_absent(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    a, doc_a, ha = _bundle(client, owner_db, make_owner_user, make_tenant, _SYN_A)
    tid = a["tenant"].id
    enc = _open_encounter(doc_a, tid, a)
    ref = _create_doc(doc_a, tid, enc["id"], ha).json()
    r = doc_a.delete(
        f"/api/v1/tenants/{tid}/encounters/{enc['id']}/documents/{ref['id']}",
        headers=ha,
    )
    assert r.status_code == 405 or r.status_code == 404


def test_p36_missing_permission_access_is_403(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    a, doc_a, ha = _bundle(client, owner_db, make_owner_user, make_tenant, _SYN_A)
    tid = a["tenant"].id
    enc = _open_encounter(doc_a, tid, a)
    ref = _create_doc(doc_a, tid, enc["id"], ha).json()
    staff = login_client(client, email=a["receptionist"].email)
    assert _access(staff, tid, ref["id"], ha).status_code == 403


def test_p36_stale_tenant_header_cannot_read(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    a, doc_a, ha = _bundle(client, owner_db, make_owner_user, make_tenant, _SYN_A)
    b, _doc_b, hb = _bundle(client, owner_db, make_owner_user, make_tenant, _SYN_B)
    enc = _open_encounter(doc_a, a["tenant"].id, a)
    ref = _create_doc(doc_a, a["tenant"].id, enc["id"], ha).json()
    # Same authenticated doctor A, but X-Tenant switched to B after create.
    assert _access(doc_a, b["tenant"].id, ref["id"], hb).status_code in (403, 404)


def test_p36_poisoned_legacy_storage_key_blocks_access(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    a, doc_a, ha = _bundle(client, owner_db, make_owner_user, make_tenant, _SYN_A)
    tid = a["tenant"].id
    enc = _open_encounter(doc_a, tid, a)
    ref = _create_doc(doc_a, tid, enc["id"], ha).json()
    # Simulate legacy row poison via owner_db (bypasses API).
    owner_db.execute(
        text(
            "UPDATE document_references SET storage_key = :k WHERE id = CAST(:id AS uuid)"
        ),
        {"k": f"tenants/{uuid.uuid4()}/stolen.png", "id": ref["id"]},
    )
    owner_db.commit()
    assert _access(doc_a, tid, ref["id"], ha).status_code == 422


def test_p36_signed_url_expiry_enforced_on_local_adapter() -> None:
    adapter = build_storage_adapter(get_settings())
    token = adapter.signed_access(key="tenants/demo/doc.png", expires_seconds=1)
    assert adapter.verify_signed_access(key="tenants/demo/doc.png", token=token)
    # Integer-second expiry: wait past the boundary with margin.
    time.sleep(2.1)
    assert not adapter.verify_signed_access(key="tenants/demo/doc.png", token=token)


def test_p36_signed_url_key_mismatch_fails() -> None:
    adapter = build_storage_adapter(get_settings())
    token = adapter.signed_access(key="tenants/a/doc.png", expires_seconds=300)
    assert not adapter.verify_signed_access(key="tenants/b/doc.png", token=token)


# ---------------------------------------------------------------------------
# Dental consent hard-gate
# ---------------------------------------------------------------------------


def test_p36_procedure_requires_granted_consent(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    a, doc_a, ha = _bundle(client, owner_db, make_owner_user, make_tenant, _SYN_A)
    tid = a["tenant"].id
    enc = _open_encounter(doc_a, tid, a)
    rec = doc_a.post(
        f"/api/v1/tenants/{tid}/encounters/{enc['id']}/procedure-records",
        json={"procedure_code": "filling", "tooth": 16, "surface": "occlusal"},
        headers=ha,
    )
    assert rec.status_code == 200, rec.text
    rid = rec.json()["id"]
    # Missing consent
    assert (
        doc_a.post(
            f"/api/v1/tenants/{tid}/procedure-records/{rid}/status",
            json={"status": "in_progress"},
            headers=ha,
        ).status_code
        == 403
    )
    cid = _grant_procedure_consent(doc_a, tid, rid, ha)
    assert (
        doc_a.post(
            f"/api/v1/tenants/{tid}/procedure-records/{rid}/status",
            json={"status": "in_progress"},
            headers=ha,
        ).status_code
        == 200
    )
    # Withdraw then block completed
    assert (
        doc_a.post(
            f"/api/v1/tenants/{tid}/consents/{cid}/withdraw", json={}, headers=ha
        ).status_code
        == 200
    )
    assert (
        doc_a.post(
            f"/api/v1/tenants/{tid}/procedure-records/{rid}/status",
            json={"status": "completed"},
            headers=ha,
        ).status_code
        == 403
    )


def test_p36_wrong_procedure_consent_does_not_unlock(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    a, doc_a, ha = _bundle(client, owner_db, make_owner_user, make_tenant, _SYN_A)
    tid = a["tenant"].id
    enc = _open_encounter(doc_a, tid, a)
    base = f"/api/v1/tenants/{tid}/encounters/{enc['id']}/procedure-records"
    r1 = doc_a.post(
        base, json={"procedure_code": "filling", "tooth": 16}, headers=ha
    ).json()
    r2 = doc_a.post(
        base, json={"procedure_code": "cleaning", "tooth": 11}, headers=ha
    ).json()
    _grant_procedure_consent(doc_a, tid, r1["id"], ha)
    assert (
        doc_a.post(
            f"/api/v1/tenants/{tid}/procedure-records/{r2['id']}/status",
            json={"status": "in_progress"},
            headers=ha,
        ).status_code
        == 403
    )


def _open_svc(owner_db, b):  # type: ignore[no-untyped-def]
    from app.modules.clinical import service as clinical_service

    return clinical_service.open_encounter(
        owner_db,
        tenant_id=b["tenant"].id,
        actor_id=b["admin"].id,
        patient_id=b["patient"].id,
        practitioner_id=b["practitioner"].id,
        location_id=b["location"].id,
    )


def test_p36_pending_and_declined_consent_fail_closed(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=f"p36-cdec-{uuid.uuid4().hex[:6]}",
        patient_name="Synthetic Consent Patient",
    )
    enc = _open_svc(owner_db, b)
    tid = b["tenant"].id
    rec = dplans.record_procedure(
        owner_db,
        tenant_id=tid,
        encounter_id=enc.id,
        practitioner_id=b["practitioner"].id,
        procedure_code="filling",
        tooth=16,
    )
    pending = dplans.create_consent(
        owner_db,
        tenant_id=tid,
        procedure_record_id=rec.id,
        consenter_name="Synthetic Pending",
    )
    with pytest.raises(ForbiddenError):
        dplans.transition_procedure_record(
            owner_db, tenant_id=tid, record_id=rec.id, to_status=DM.RECORD_IN_PROGRESS
        )
    dplans.decide_consent(
        owner_db,
        tenant_id=tid,
        consent_id=pending.id,
        decision=DM.CONSENT_DECLINED,
        actor_id=b["admin"].id,
    )
    with pytest.raises(ForbiddenError):
        dplans.transition_procedure_record(
            owner_db, tenant_id=tid, record_id=rec.id, to_status=DM.RECORD_IN_PROGRESS
        )


def test_p36_cancel_without_consent_allowed(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=f"p36-cancel-{uuid.uuid4().hex[:6]}",
        patient_name="Synthetic Cancel Patient",
    )
    enc = _open_svc(owner_db, b)
    tid = b["tenant"].id
    rec = dplans.record_procedure(
        owner_db,
        tenant_id=tid,
        encounter_id=enc.id,
        practitioner_id=b["practitioner"].id,
        procedure_code="filling",
        tooth=16,
    )
    cancelled = dplans.transition_procedure_record(
        owner_db, tenant_id=tid, record_id=rec.id, to_status=DM.RECORD_CANCELLED
    )
    assert cancelled.status == DM.RECORD_CANCELLED


def test_p36_cross_tenant_consent_subject_is_404(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    a, doc_a, ha = _bundle(client, owner_db, make_owner_user, make_tenant, _SYN_A)
    b, doc_b, hb = _bundle(client, owner_db, make_owner_user, make_tenant, _SYN_B)
    enc = _open_encounter(doc_a, a["tenant"].id, a)
    rec = doc_a.post(
        f"/api/v1/tenants/{a['tenant'].id}/encounters/{enc['id']}/procedure-records",
        json={"procedure_code": "filling", "tooth": 16},
        headers=ha,
    ).json()
    # Tenant B cannot attach consent to A's procedure record.
    r = doc_b.post(
        f"/api/v1/tenants/{b['tenant'].id}/consents",
        json={
            "procedure_record_id": rec["id"],
            "consenter_name": "Synthetic Intruder",
        },
        headers=hb,
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Broader tenant isolation (API + RLS spot checks)
# ---------------------------------------------------------------------------


def test_p36_patient_search_isolation(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    a, doc_a, ha = _bundle(client, owner_db, make_owner_user, make_tenant, _SYN_A)
    b, doc_b, hb = _bundle(client, owner_db, make_owner_user, make_tenant, _SYN_B)
    listed_b = doc_b.get(
        f"/api/v1/tenants/{b['tenant'].id}/patients",
        headers=hb,
        params={"q": "Synthetic Patient A1"},
    )
    assert listed_b.status_code == 200
    names = [p.get("display_name", "") for p in listed_b.json()]
    assert all("A1" not in n for n in names)
    # Direct IDOR
    r = doc_b.get(
        f"/api/v1/tenants/{b['tenant'].id}/patients/{a['patient'].id}", headers=hb
    )
    assert r.status_code in (404, 403)


def test_p36_rls_blocks_cross_tenant_document_select(
    owner_db, app_factory, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    """Database-level: app role with tenant B context cannot see A docs."""
    a = provision_clinical(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=f"p36-rls-a-{uuid.uuid4().hex[:6]}",
        patient_name="Synthetic RLS A",
    )
    b = provision_clinical(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=f"p36-rls-b-{uuid.uuid4().hex[:6]}",
        patient_name="Synthetic RLS B",
    )
    enc = _open_svc(owner_db, a)
    ref = dplans.create_document_ref(
        owner_db,
        tenant_id=a["tenant"].id,
        encounter_id=enc.id,
        actor_id=a["admin"].id,
        doc_type="xray",
        content_type="image/png",
    )
    owner_db.commit()

    with app_factory() as s:
        s.execute(
            text("SELECT set_config('app.tenant_id', :t, false)"),
            {"t": str(b["tenant"].id)},
        )
        rows = s.execute(
            text("SELECT id FROM document_references WHERE id = CAST(:id AS uuid)"),
            {"id": str(ref.id)},
        ).all()
        assert rows == []
        s.rollback()
