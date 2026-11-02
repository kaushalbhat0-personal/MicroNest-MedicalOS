"""Clinical + prescription API: lifecycle, validation, pagination, audit
side-effects over HTTP. Doctor login carries a practitioner profile; admin
login does not (403 on authoring endpoints)."""

from __future__ import annotations

from tests.helpers import login_client, provision_clinical, tenant_headers


def _setup(client, owner_db, make_owner_user, make_tenant, **kw):  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant, **kw)
    doc = login_client(client, email=b["doctor"].email)
    adm = login_client(client, email=b["admin"].email)
    h = tenant_headers(b["tenant"].id)
    return b, doc, adm, h


def _open(c, tid, b, **kw):  # type: ignore[no-untyped-def]
    body = {
        "patient_id": str(b["patient"].id),
        "practitioner_id": str(b["practitioner"].id),
        "location_id": str(b["location"].id),
    }
    body.update(kw)
    r = c.post(
        f"/api/v1/tenants/{tid}/encounters", json=body, headers=tenant_headers(tid)
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_encounter_open_list_close(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b, doc, _, h = _setup(client, owner_db, make_owner_user, make_tenant)
    tid = b["tenant"].id
    e = _open(doc, tid, b)
    listed = doc.get(f"/api/v1/tenants/{tid}/encounters", headers=h).json()
    assert listed["items"] and listed["items"][0]["id"] == e["id"]
    # Close blocked: no note, no vitals, no waivers.
    r = doc.post(
        f"/api/v1/tenants/{tid}/encounters/{e['id']}/close", json={}, headers=h
    )
    assert r.status_code == 422, r.text
    # Add finalized note + vitals, then close.
    note = doc.post(
        f"/api/v1/tenants/{tid}/encounters/{e['id']}/clinical-notes",
        json={"assessment": "viral URI"},
        headers=h,
    )
    assert note.status_code == 200, note.text
    fin = doc.post(
        f"/api/v1/tenants/{tid}/clinical-notes/{note.json()['id']}/finalize",
        json={},
        headers=h,
    )
    assert fin.status_code == 200, fin.text
    obs = doc.post(
        f"/api/v1/tenants/{tid}/encounters/{e['id']}/observations",
        json={"type_code": "pulse", "value_numeric": 72},
        headers=h,
    )
    assert obs.status_code == 200, obs.text
    closed = doc.post(
        f"/api/v1/tenants/{tid}/encounters/{e['id']}/close", json={}, headers=h
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "closed"
    again = doc.post(
        f"/api/v1/tenants/{tid}/encounters/{e['id']}/close",
        json={"note_waiver": True, "vitals_waiver": True},
        headers=h,
    )
    assert again.status_code == 409


def test_admin_without_practitioner_profile_cannot_author(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b, doc, adm, h = _setup(client, owner_db, make_owner_user, make_tenant)
    tid = b["tenant"].id
    e = _open(doc, tid, b)
    r = adm.post(
        f"/api/v1/tenants/{tid}/encounters/{e['id']}/clinical-notes",
        json={"assessment": "x"},
        headers=h,
    )
    assert r.status_code == 403, r.text


def test_note_amend_and_finalize_rules(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b, doc, _, h = _setup(client, owner_db, make_owner_user, make_tenant)
    tid = b["tenant"].id
    e = _open(doc, tid, b)
    base = f"/api/v1/tenants/{tid}/encounters/{e['id']}/clinical-notes"
    assert doc.post(base, json={}, headers=h).status_code == 422
    note = doc.post(base, json={"assessment": "initial"}, headers=h).json()
    amend_draft = doc.post(
        f"/api/v1/tenants/{tid}/clinical-notes/{note['id']}/amend",
        json={"assessment": "too soon"},
        headers=h,
    )
    assert amend_draft.status_code == 409
    assert (
        doc.post(
            f"/api/v1/tenants/{tid}/clinical-notes/{note['id']}/finalize",
            json={},
            headers=h,
        ).status_code
        == 200
    )
    fixed = doc.post(
        f"/api/v1/tenants/{tid}/clinical-notes/{note['id']}/amend",
        json={"assessment": "corrected"},
        headers=h,
    )
    assert fixed.status_code == 200, fixed.text
    assert fixed.json()["assessment"] == "corrected"
    assert fixed.json()["supersedes_id"] == note["id"]


def test_observation_validation_and_amend(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b, doc, _, h = _setup(client, owner_db, make_owner_user, make_tenant)
    tid = b["tenant"].id
    e = _open(doc, tid, b)
    base = f"/api/v1/tenants/{tid}/encounters/{e['id']}/observations"
    bad = doc.post(
        base, json={"type_code": "bp_systolic", "value_numeric": 500}, headers=h
    )
    assert bad.status_code == 422
    obs = doc.post(
        base, json={"type_code": "temperature", "value_numeric": 37.2}, headers=h
    )
    assert obs.status_code == 200, obs.text
    assert obs.json()["value_numeric"] == 37.2
    assert obs.json()["unit"] == "°C"
    fixed = doc.post(
        f"/api/v1/tenants/{tid}/observations/{obs.json()['id']}/amend",
        json={"type_code": "temperature", "value_numeric": 38.1},
        headers=h,
    )
    assert fixed.status_code == 200
    types = doc.get(f"/api/v1/tenants/{tid}/observation-types", headers=h).json()
    assert {t["code"] for t in types} >= {"bp_systolic", "pulse", "spo2"}


def test_diagnosis_flow(client, owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b, doc, _, h = _setup(client, owner_db, make_owner_user, make_tenant)
    tid = b["tenant"].id
    e = _open(doc, tid, b)
    base = f"/api/v1/tenants/{tid}/encounters/{e['id']}/diagnoses"
    dx = doc.post(base, json={"diagnosis_code": "K02.9", "is_primary": True}, headers=h)
    assert dx.status_code == 200, dx.text
    free = doc.post(base, json={"free_text": "watch 16"}, headers=h)
    assert free.status_code == 200, free.text
    both = doc.post(base, json={"diagnosis_code": "K02.9", "free_text": "x"}, headers=h)
    assert both.status_code == 422
    neither = doc.post(base, json={}, headers=h)
    assert neither.status_code == 422
    codes = doc.get(f"/api/v1/tenants/{tid}/diagnosis-codes", headers=h).json()
    assert any(c["code"] == "K02.9" and c["icd10"] == "K02.9" for c in codes)
    res = doc.post(
        f"/api/v1/tenants/{tid}/diagnoses/{dx.json()['id']}/resolve",
        json={"outcome": "resolved"},
        headers=h,
    )
    assert res.status_code == 200
    sup = doc.post(
        f"/api/v1/tenants/{tid}/diagnoses/{free.json()['id']}/supersede",
        json={"diagnosis_code": "K04.7"},
        headers=h,
    )
    assert sup.status_code == 200, sup.text
    assert sup.json()["diagnosis_code"] == "K04.7"


def test_prescription_lifecycle(client, owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b, doc, _, h = _setup(client, owner_db, make_owner_user, make_tenant)
    tid = b["tenant"].id
    e = _open(doc, tid, b)
    meds = doc.get(f"/api/v1/tenants/{tid}/medications", headers=h).json()
    assert any(m["code"] == "paracetamol-650" for m in meds)
    item = {
        "medication_code": "paracetamol-650",
        "dose": "650 mg",
        "route": "oral",
        "frequency": "TID",
        "instructions": "after food",
    }
    base = f"/api/v1/tenants/{tid}/encounters/{e['id']}/prescriptions"
    bad = doc.post(
        base, json={"items": [{**item, "medication_code": "nope"}]}, headers=h
    )
    assert bad.status_code == 422
    p = doc.post(base, json={"items": [item]}, headers=h)
    assert p.status_code == 200, p.text
    pid = p.json()["id"]
    assert p.json()["items"][0]["medication_name"] == "Paracetamol"
    assert (
        doc.post(
            f"/api/v1/tenants/{tid}/prescriptions/{pid}/sign", json={}, headers=h
        ).status_code
        == 200
    )
    again = doc.post(
        f"/api/v1/tenants/{tid}/prescriptions/{pid}/sign", json={}, headers=h
    )
    assert again.status_code == 409
    corr = doc.post(
        f"/api/v1/tenants/{tid}/prescriptions/{pid}/correct",
        json={"items": [{**item, "frequency": "BID"}]},
        headers=h,
    )
    assert corr.status_code == 200, corr.text
    assert corr.json()["version"] == 2
    assert corr.json()["status"] == "draft"


def test_receptionist_can_open_but_not_read_clinical(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from app.modules.tenancy import service as tenancy_service
    from tests.helpers import login_client

    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    tid = b["tenant"].id
    recep = make_owner_user(email="recep-clin@example.com")
    tenancy_service.create_membership(
        owner_db,
        user=recep,
        tenant=b["tenant"],
        role=tenancy_service.get_seed_role(owner_db, "receptionist"),
    )
    owner_db.commit()
    rc = login_client(client, email="recep-clin@example.com")
    h = tenant_headers(tid)
    opened = rc.post(
        f"/api/v1/tenants/{tid}/encounters",
        json={
            "patient_id": str(b["patient"].id),
            "practitioner_id": str(b["practitioner"].id),
            "location_id": str(b["location"].id),
        },
        headers=h,
    )
    assert opened.status_code == 200, opened.text
    assert rc.get(f"/api/v1/tenants/{tid}/encounters", headers=h).status_code == 200
    # Receptionist has no clinical.create: note write denied.
    denied = rc.post(
        f"/api/v1/tenants/{tid}/encounters/{opened.json()['id']}/clinical-notes",
        json={"assessment": "x"},
        headers=h,
    )
    assert denied.status_code == 403


def test_clinical_audit_carries_no_content(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import text

    b, doc, _, h = _setup(client, owner_db, make_owner_user, make_tenant)
    tid = b["tenant"].id
    e = _open(doc, tid, b)
    marker = "soap-marker-xyz-unique"
    note = doc.post(
        f"/api/v1/tenants/{tid}/encounters/{e['id']}/clinical-notes",
        json={"subjective": marker, "assessment": "a"},
        headers=h,
    )
    assert note.status_code == 200, note.text
    doc.post(
        f"/api/v1/tenants/{tid}/clinical-notes/{note.json()['id']}/finalize",
        json={},
        headers=h,
    )
    rows = owner_db.execute(
        text("SELECT action, reason FROM audit_events WHERE tenant_id = :t"),
        {"t": str(tid)},
    ).fetchall()
    blob = " ".join(f"{a} {r}" for a, r in rows)
    assert marker not in blob
    assert all(r is None for _, r in rows)
