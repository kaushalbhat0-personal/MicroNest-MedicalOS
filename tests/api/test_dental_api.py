"""Dental API: findings, plans, procedure records, consents, recalls,
document references. Provider attribution is server-derived (doctor login
carries a practitioner profile)."""

from __future__ import annotations

from datetime import date

from tests.helpers import login_client, provision_clinical, tenant_headers


def _setup(client, owner_db, make_owner_user, make_tenant, **kw):  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant, **kw)
    doc = login_client(client, email=b["doctor"].email)
    h = tenant_headers(b["tenant"].id)
    return b, doc, h


def _open(c, tid, b):  # type: ignore[no-untyped-def]
    r = c.post(
        f"/api/v1/tenants/{tid}/encounters",
        json={
            "patient_id": str(b["patient"].id),
            "practitioner_id": str(b["practitioner"].id),
            "location_id": str(b["location"].id),
        },
        headers=tenant_headers(tid),
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_finding_lifecycle(client, owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b, doc, h = _setup(client, owner_db, make_owner_user, make_tenant)
    tid = b["tenant"].id
    e = _open(doc, tid, b)
    conds = doc.get(f"/api/v1/tenants/{tid}/dental-conditions", headers=h).json()
    assert any(c["code"] == "caries" for c in conds)
    base = f"/api/v1/tenants/{tid}/encounters/{e['id']}/tooth-findings"
    bad_tooth = doc.post(
        base, json={"tooth": 99, "condition_code": "caries"}, headers=h
    )
    assert bad_tooth.status_code == 422
    bad_surface = doc.post(
        base,
        json={"tooth": 16, "condition_code": "caries", "surfaces": ["tentacle"]},
        headers=h,
    )
    assert bad_surface.status_code == 422
    f = doc.post(
        base,
        json={
            "tooth": 16,
            "condition_code": "caries",
            "surfaces": ["mesial", "occlusal"],
        },
        headers=h,
    )
    assert f.status_code == 200, f.text
    assert f.json()["surfaces"] == ["mesial", "occlusal"]
    listed = doc.get(base, headers=h).json()
    assert len(listed) == 1 and listed[0]["condition_display"]
    res = doc.post(
        f"/api/v1/tenants/{tid}/tooth-findings/{f.json()['id']}/resolve",
        json={},
        headers=h,
    )
    assert res.status_code == 200
    assert res.json()["status"] == "resolved"
    assert (
        doc.post(
            f"/api/v1/tenants/{tid}/tooth-findings/{f.json()['id']}/resolve",
            json={},
            headers=h,
        ).status_code
        == 409
    )


def test_plan_lifecycle_with_consent(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b, doc, h = _setup(client, owner_db, make_owner_user, make_tenant)
    tid = b["tenant"].id
    e = _open(doc, tid, b)
    procs = doc.get(f"/api/v1/tenants/{tid}/dental-procedures", headers=h).json()
    assert any(p["code"] == "filling" for p in procs)
    plan = doc.post(
        f"/api/v1/tenants/{tid}/treatment-plans",
        json={
            "patient_id": str(b["patient"].id),
            "encounter_id": e["id"],
            "practitioner_id": str(b["practitioner"].id),
            "notes": "MOD on 16",
            "items": [
                {
                    "procedure_code": "filling",
                    "tooth": 16,
                    "surface": "occlusal",
                    "sequence": 1,
                }
            ],
        },
        headers=h,
    )
    assert plan.status_code == 200, plan.text
    pid = plan.json()["id"]
    assert len(plan.json()["items"]) == 1
    assert plan.json()["status"] == "draft"
    # Activate with item, complete only after item completes.
    assert (
        doc.post(
            f"/api/v1/tenants/{tid}/treatment-plans/{pid}/activate", json={}, headers=h
        ).status_code
        == 200
    )
    item_id = plan.json()["items"][0]["id"]
    assert (
        doc.post(
            f"/api/v1/tenants/{tid}/plan-items/{item_id}/status",
            json={"status": "planned"},
            headers=h,
        ).status_code
        == 200
    )
    # Consent for the plan.
    consent = doc.post(
        f"/api/v1/tenants/{tid}/consents",
        json={
            "plan_id": pid,
            "consenter_name": "Pat Clinical",
            "consenter_relation": "self",
        },
        headers=h,
    )
    assert consent.status_code == 200, consent.text
    cid = consent.json()["id"]
    decide = doc.post(
        f"/api/v1/tenants/{tid}/consents/{cid}/decide",
        json={"decision": "granted"},
        headers=h,
    )
    assert decide.status_code == 200
    withdraw = doc.post(
        f"/api/v1/tenants/{tid}/consents/{cid}/withdraw", json={}, headers=h
    )
    assert withdraw.status_code == 200
    assert withdraw.json()["status"] == "withdrawn"
    # Finish the item, then the plan.
    for nxt in ("in_progress", "completed"):
        r = doc.post(
            f"/api/v1/tenants/{tid}/plan-items/{item_id}/status",
            json={"status": nxt},
            headers=h,
        )
        assert r.status_code == 200, r.text
    done = doc.post(
        f"/api/v1/tenants/{tid}/treatment-plans/{pid}/complete", json={}, headers=h
    )
    assert done.status_code == 200
    assert done.json()["status"] == "completed"


def test_procedure_record_lifecycle(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b, doc, h = _setup(client, owner_db, make_owner_user, make_tenant)
    tid = b["tenant"].id
    e = _open(doc, tid, b)
    base = f"/api/v1/tenants/{tid}/encounters/{e['id']}/procedure-records"
    r = doc.post(
        base,
        json={"procedure_code": "filling", "tooth": 16, "surface": "occlusal"},
        headers=h,
    )
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    for nxt in ("in_progress", "completed"):
        s = doc.post(
            f"/api/v1/tenants/{tid}/procedure-records/{rid}/status",
            json={"status": nxt},
            headers=h,
        )
        assert s.status_code == 200, s.text
    assert s.json()["performed_at"] is not None
    listed = doc.get(base, headers=h).json()
    assert len(listed) == 1


def test_recall_and_document_flow(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b, doc, h = _setup(client, owner_db, make_owner_user, make_tenant)
    tid = b["tenant"].id
    e = _open(doc, tid, b)
    recall = doc.post(
        f"/api/v1/tenants/{tid}/recalls",
        json={
            "patient_id": str(b["patient"].id),
            "practitioner_id": str(b["practitioner"].id),
            "location_id": str(b["location"].id),
            "due_date": date(2027, 6, 1).isoformat(),
            "reason": "six-month review",
        },
        headers=h,
    )
    assert recall.status_code == 200, recall.text
    listed = doc.get(
        f"/api/v1/tenants/{tid}/recalls",
        params={"patient_id": str(b["patient"].id)},
        headers=h,
    ).json()
    assert len(listed) == 1
    done = doc.post(
        f"/api/v1/tenants/{tid}/recalls/{recall.json()['id']}/status",
        json={"status": "completed"},
        headers=h,
    )
    assert done.status_code == 200
    docref = doc.post(
        f"/api/v1/tenants/{tid}/encounters/{e['id']}/documents",
        json={"doc_type": "xray", "storage_key": "t/x/16.png", "sha256": "abc123"},
        headers=h,
    )
    assert docref.status_code == 200, docref.text
    docs = doc.get(
        f"/api/v1/tenants/{tid}/encounters/{e['id']}/documents", headers=h
    ).json()
    assert len(docs) == 1 and docs[0]["storage_key"] == "t/x/16.png"


def test_cancel_plan_cascades_items(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b, doc, h = _setup(client, owner_db, make_owner_user, make_tenant)
    tid = b["tenant"].id
    plan = doc.post(
        f"/api/v1/tenants/{tid}/treatment-plans",
        json={
            "patient_id": str(b["patient"].id),
            "practitioner_id": str(b["practitioner"].id),
            "items": [{"procedure_code": "cleaning", "sequence": 1}],
        },
        headers=h,
    ).json()
    cancelled = doc.post(
        f"/api/v1/tenants/{tid}/treatment-plans/{plan['id']}/cancel", json={}, headers=h
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["items"][0]["status"] == "cancelled"
