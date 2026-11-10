"""Document access grants: authorized, short-lived signed URLs for eligible
image references. UUID opacity is never the control — every case below
exercises the server-side authorization boundary."""

from __future__ import annotations

import uuid

from sqlalchemy import text

from tests.helpers import login_client, provision_clinical, tenant_headers


def _setup(client, owner_db, make_owner_user, make_tenant, **kw):  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant, **kw)
    doc = login_client(client, email=b["doctor"].email)
    h = tenant_headers(b["tenant"].id)
    return b, doc, h


def _open(c, tid, b, location=None):  # type: ignore[no-untyped-def]
    r = c.post(
        f"/api/v1/tenants/{tid}/encounters",
        json={
            "patient_id": str(b["patient"].id),
            "practitioner_id": str(b["practitioner"].id),
            "location_id": str((location or b["location"]).id),
        },
        headers=tenant_headers(tid),
    )
    assert r.status_code == 200, r.text
    return r.json()


def _image_ref(c, tid, encounter_id, h, **kw):  # type: ignore[no-untyped-def]
    body = {
        "doc_type": "xray",
        "storage_key": f"t/x/{uuid.uuid4().hex[:8]}.png",
        "content_type": "image/png",
        "sha256": "abc123",
    }
    body.update(kw)
    r = c.post(
        f"/api/v1/tenants/{tid}/encounters/{encounter_id}/documents",
        json=body,
        headers=h,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _access(c, tid, document_id, h, json=None):  # type: ignore[no-untyped-def]
    return c.post(
        f"/api/v1/tenants/{tid}/documents/{document_id}/access",
        json=json or {},
        headers=h,
    )


def test_access_grants_short_lived_url_without_storage_key(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b, doc, h = _setup(client, owner_db, make_owner_user, make_tenant)
    tid = b["tenant"].id
    e = _open(doc, tid, b)
    ref = _image_ref(doc, tid, e["id"], h)
    r = _access(doc, tid, ref["id"], h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["document_id"] == ref["id"]
    assert body["expires_in_seconds"] == 300
    assert body["content_type"] == "image/png"
    assert body["url"], "signed URL must be returned"
    assert "url" in body and "storage_key" not in body
    assert ref["storage_key"] not in r.text, "storage key must never leave the server"
    # Audit carries opaque ids only: no URL, key, or clinical content.
    rows = owner_db.execute(
        text(
            "SELECT action, resource_type, resource_id, reason, encounter_id "
            "FROM audit_events WHERE action = 'document.access_granted'"
        )
    ).all()
    assert len(rows) == 1
    action, rtype, rid, reason, _enc = rows[0]
    assert (action, rtype, rid) == ("document.access_granted", "document", ref["id"])
    assert reason is None
    assert body["url"] not in (reason or "")


def test_unauthenticated_access_is_401(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b, doc, h = _setup(client, owner_db, make_owner_user, make_tenant)
    tid = b["tenant"].id
    e = _open(doc, tid, b)
    ref = _image_ref(doc, tid, e["id"], h)
    r = client.post(
        f"/api/v1/tenants/{tid}/documents/{ref['id']}/access",
        json={},
        headers=tenant_headers(tid),
    )
    assert r.status_code == 401


def test_role_without_dental_read_is_403(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from app.modules.tenancy import service as tenancy_service

    b, doc, h = _setup(client, owner_db, make_owner_user, make_tenant)
    tid = b["tenant"].id
    e = _open(doc, tid, b)
    ref = _image_ref(doc, tid, e["id"], h)
    viewer = make_owner_user(email="staff-doc-access@example.com")
    tenancy_service.create_membership(
        owner_db,
        user=viewer,
        tenant=b["tenant"],
        role=tenancy_service.get_seed_role(owner_db, "staff"),
    )
    owner_db.commit()
    vc = login_client(client, email="staff-doc-access@example.com")
    assert _access(vc, tid, ref["id"], h).status_code == 403


def test_cross_tenant_access_is_404(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b, doc, h = _setup(client, owner_db, make_owner_user, make_tenant, slug="doc-acc-a")
    tid = b["tenant"].id
    e = _open(doc, tid, b)
    ref = _image_ref(doc, tid, e["id"], h)
    b2, doc2, h2 = _setup(
        client, owner_db, make_owner_user, make_tenant, slug="doc-acc-b"
    )
    tid2 = b2["tenant"].id
    # Other tenant's user against their own path tenant: target belongs
    # elsewhere, so the probe learns nothing (404, never 403-oracle).
    assert _access(doc2, tid2, ref["id"], h2).status_code == 404
    # Path-tenant mismatch is also 404, never a cross-tenant read.
    assert _access(doc2, tid, ref["id"], h2).status_code == 404


def test_out_of_scope_location_is_403(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from app.modules.clinics import service as clinics_service
    from app.modules.tenancy import service as tenancy_service

    b, doc, h = _setup(
        client, owner_db, make_owner_user, make_tenant, slug="doc-acc-loc"
    )
    tid = b["tenant"].id
    loc2 = clinics_service.create_location(owner_db, tenant=b["tenant"], name="Annex")
    owner_db.commit()
    e2 = _open(doc, tid, b, location=loc2)
    ref = _image_ref(doc, tid, e2["id"], h)
    scoped_user = make_owner_user(email="scoped-doc-access@example.com")
    tenancy_service.create_membership(
        owner_db,
        user=scoped_user,
        tenant=b["tenant"],
        role=tenancy_service.get_seed_role(owner_db, "doctor"),
        location_ids=[b["location"].id],
    )
    owner_db.commit()
    cc = login_client(client, email="scoped-doc-access@example.com")
    assert _access(cc, tid, ref["id"], h).status_code == 403


def test_unknown_document_is_404(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b, doc, h = _setup(client, owner_db, make_owner_user, make_tenant)
    assert _access(doc, b["tenant"].id, uuid.uuid4(), h).status_code == 404


def test_non_image_document_is_422(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b, doc, h = _setup(client, owner_db, make_owner_user, make_tenant)
    tid = b["tenant"].id
    e = _open(doc, tid, b)
    report = _image_ref(
        doc,
        tid,
        e["id"],
        h,
        doc_type="report",
        storage_key=f"t/r/{uuid.uuid4().hex[:8]}.pdf",
        content_type="application/pdf",
    )
    assert _access(doc, tid, report["id"], h).status_code == 422
    untyped = _image_ref(
        doc,
        tid,
        e["id"],
        h,
        doc_type="other",
        storage_key=f"t/r/{uuid.uuid4().hex[:8]}.bin",
        content_type=None,
    )
    assert _access(doc, tid, untyped["id"], h).status_code == 422


def test_storage_unavailable_is_503(
    client, owner_db, make_owner_user, make_tenant, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    import app.api.v1.dental as dental_api

    b, doc, h = _setup(client, owner_db, make_owner_user, make_tenant)
    tid = b["tenant"].id
    e = _open(doc, tid, b)
    ref = _image_ref(doc, tid, e["id"], h)

    def _boom(settings):  # type: ignore[no-untyped-def]
        raise RuntimeError("no storage configured")

    monkeypatch.setattr(dental_api, "build_storage_adapter", _boom)
    r = _access(doc, tid, ref["id"], h)
    assert r.status_code == 503
    assert r.json()["title"] == "service unavailable"


def test_client_cannot_control_key_or_expiry(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b, doc, h = _setup(client, owner_db, make_owner_user, make_tenant)
    tid = b["tenant"].id
    e = _open(doc, tid, b)
    ref = _image_ref(doc, tid, e["id"], h)
    # The endpoint takes no body: injected keys/expiry must be ignored.
    r = _access(
        doc,
        tid,
        ref["id"],
        h,
        json={"storage_key": "evil/key.png", "expires_seconds": 99999},
    )
    assert r.status_code == 200, r.text
    assert r.json()["expires_in_seconds"] == 300
    assert "evil" not in r.text


def test_same_scope_other_patient_follows_existing_read_model(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    """Provider reads are tenant+location scoped, not per-patient grants
    (that is the existing model, also used by list/findings/plans). A second
    patient's image in the same scope is therefore readable — recorded here
    so the rule stays explicit and cannot drift silently."""
    from app.modules.patients import service as patients_service

    b, doc, h = _setup(client, owner_db, make_owner_user, make_tenant)
    tid = b["tenant"].id
    other = patients_service.register_patient(
        owner_db, tenant_id=b["tenant"].id, display_name="Pat Other"
    )
    owner_db.commit()
    r = doc.post(
        f"/api/v1/tenants/{tid}/encounters",
        json={
            "patient_id": str(other.id),
            "practitioner_id": str(b["practitioner"].id),
            "location_id": str(b["location"].id),
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    ref = _image_ref(doc, tid, r.json()["id"], h)
    assert _access(doc, tid, ref["id"], h).status_code == 200


def test_metadata_listing_shape_is_unchanged(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b, doc, h = _setup(client, owner_db, make_owner_user, make_tenant)
    tid = b["tenant"].id
    e = _open(doc, tid, b)
    _image_ref(doc, tid, e["id"], h)
    listed = doc.get(
        f"/api/v1/tenants/{tid}/encounters/{e['id']}/documents", headers=h
    ).json()
    assert len(listed) == 1
    assert "url" not in listed[0], "metadata listing must not mint URLs"
    assert set(listed[0]) == {
        "id",
        "tenant_id",
        "encounter_id",
        "doc_type",
        "storage_key",
        "content_type",
        "size_bytes",
        "sha256",
        "notes",
        "created_at",
    }
