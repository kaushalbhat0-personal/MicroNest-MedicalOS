"""Estimate API: CRUD, money strings, pagination, IDOR, audit."""

from __future__ import annotations

import uuid
from decimal import Decimal

from tests.helpers import login_client, provision_clinical, tenant_headers


def _body(b, **kw):  # type: ignore[no-untyped-def]
    args = {
        "patient_id": str(b["patient"].id),
        "location_id": str(b["location"].id),
        "items": [
            {
                "description": "Filling",
                "quantity": "2",
                "unit_rate": "200.00",
                "tax_rate": "18",
            }
        ],
    }
    args.update(kw)
    return args


def _scoped_doctor(owner_db, make_owner_user, tenant, location_ids, email):  # type: ignore[no-untyped-def]
    from app.modules.tenancy import service as tenancy_service

    user = make_owner_user(email=email)
    tenancy_service.create_membership(
        owner_db,
        user=user,
        tenant=tenant,
        role=tenancy_service.get_seed_role(owner_db, "doctor"),
        location_ids=location_ids,
    )
    owner_db.commit()
    return user


def test_crud_and_money_strings(client, owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="est-api-a")
    doc = login_client(client, email=b["admin"].email)
    tid = b["tenant"].id
    h = tenant_headers(tid)
    created = doc.post(f"/api/v1/tenants/{tid}/estimates", json=_body(b), headers=h)
    assert created.status_code == 200, created.text
    item = created.json()
    assert item["status"] == "draft"
    # Money serializes as exact decimal strings, never floats.
    assert item["grand_total"] == "472.00"  # 2×200=400 +18% → 472
    assert Decimal(item["grand_total"]) == Decimal("472.00")
    assert "e" not in item["grand_total"].lower()
    line = item["lines"][0]
    assert line["unit_rate"] == "200.00" and line["line_total"] == "472.00"
    eid = item["id"]
    got = doc.get(f"/api/v1/tenants/{tid}/estimates/{eid}", headers=h)
    assert got.status_code == 200, got.text
    assert got.json()["id"] == eid
    patched = doc.patch(
        f"/api/v1/tenants/{tid}/estimates/{eid}", json={"notes": "hello"}, headers=h
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["notes"] == "hello"
    issued = doc.post(
        f"/api/v1/tenants/{tid}/estimates/{eid}/issue", json={}, headers=h
    )
    assert issued.status_code == 200, issued.text
    assert issued.json()["status"] == "issued"
    # Frozen: draft mutations rejected on issued estimates.
    assert (
        doc.patch(
            f"/api/v1/tenants/{tid}/estimates/{eid}", json={"notes": "x"}, headers=h
        ).status_code
        == 409
    )
    assert (
        doc.post(
            f"/api/v1/tenants/{tid}/estimates/{eid}/lines",
            json={"description": "late", "quantity": "1", "unit_rate": "10.00"},
            headers=h,
        ).status_code
        == 409
    )
    line_id = item["lines"][0]["id"]
    assert (
        doc.patch(
            f"/api/v1/tenants/{tid}/estimate-lines/{line_id}",
            json={"quantity": "9"},
            headers=h,
        ).status_code
        == 409
    )
    assert (
        doc.delete(
            f"/api/v1/tenants/{tid}/estimate-lines/{line_id}", headers=h
        ).status_code
        == 409
    )
    cancelled = doc.post(
        f"/api/v1/tenants/{tid}/estimates/{eid}/cancel", json={}, headers=h
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"


def test_pagination_and_filters(client, owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="est-api-p")
    doc = login_client(client, email=b["admin"].email)
    tid = b["tenant"].id
    h = tenant_headers(tid)
    for _ in range(3):
        r = doc.post(f"/api/v1/tenants/{tid}/estimates", json=_body(b), headers=h)
        assert r.status_code == 200, r.text
    page1 = doc.get(f"/api/v1/tenants/{tid}/estimates?limit=2", headers=h)
    assert page1.status_code == 200, page1.text
    assert len(page1.json()["items"]) == 2
    assert page1.json()["next_cursor"] is not None
    page2 = doc.get(
        f"/api/v1/tenants/{tid}/estimates?limit=2&cursor={page1.json()['next_cursor']}",
        headers=h,
    )
    assert page2.status_code == 200, page2.text
    assert len(page2.json()["items"]) == 1
    assert page2.json()["next_cursor"] is None
    by_status = doc.get(f"/api/v1/tenants/{tid}/estimates?status=draft", headers=h)
    assert by_status.status_code == 200
    assert all(i["status"] == "draft" for i in by_status.json()["items"])
    by_patient = doc.get(
        f"/api/v1/tenants/{tid}/estimates?patient_id={b['patient'].id}", headers=h
    )
    assert by_patient.status_code == 200
    assert len(by_patient.json()["items"]) == 3


def test_idor_and_location_scope(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from app.modules.clinics import service as clinics_service

    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="est-api-s")
    tid = b["tenant"].id
    h = tenant_headers(tid)
    doc = login_client(client, email=b["admin"].email)
    loc2 = clinics_service.create_location(owner_db, tenant=b["tenant"], name="Annex")
    owner_db.commit()
    _scoped_doctor(
        owner_db, make_owner_user, b["tenant"], [loc2.id], "scoped-est@example.com"
    )
    scoped = login_client(client, email="scoped-est@example.com")
    created = doc.post(f"/api/v1/tenants/{tid}/estimates", json=_body(b), headers=h)
    eid = created.json()["id"]
    # Same tenant, out-of-scope location → denied.
    assert (
        doc.get(f"/api/v1/tenants/{tid}/estimates/{eid}", headers=h).status_code == 200
    )
    assert (
        scoped.get(f"/api/v1/tenants/{tid}/estimates/{eid}", headers=h).status_code
        == 403
    )
    assert (
        scoped.post(
            f"/api/v1/tenants/{tid}/estimates", json=_body(b), headers=h
        ).status_code
        == 403
    )
    # Cross-tenant probe → 404 oracle.
    other = provision_clinical(owner_db, make_owner_user, make_tenant, slug="est-api-t")
    ho = tenant_headers(other["tenant"].id)
    other_login = login_client(client, email=other["admin"].email)
    assert (
        other_login.get(
            f"/api/v1/tenants/{other['tenant'].id}/estimates/{eid}", headers=ho
        ).status_code
        == 404
    )
    assert (
        doc.get(
            f"/api/v1/tenants/{other['tenant'].id}/estimates/{eid}", headers=h
        ).status_code
        == 404
    )


def test_estimate_auth_gates(client, owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    from app.modules.tenancy import service as tenancy_service

    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="est-api-g")
    tid = b["tenant"].id
    h = tenant_headers(tid)
    for role, email in (
        ("accountant", "acct-est@example.com"),
        ("receptionist", "recep-est@example.com"),
    ):
        user = make_owner_user(email=email)
        tenancy_service.create_membership(
            owner_db,
            user=user,
            tenant=b["tenant"],
            role=tenancy_service.get_seed_role(owner_db, role),
        )
        owner_db.commit()
    acct = login_client(client, email="acct-est@example.com")
    recep = login_client(client, email="recep-est@example.com")
    doc = login_client(client, email=b["doctor"].email)
    # Accountant: full billing authority including estimates.
    assert (
        acct.post(
            f"/api/v1/tenants/{tid}/estimates", json=_body(b), headers=h
        ).status_code
        == 200
    )
    # Doctor: billing.create covers estimate workflows.
    r = doc.post(f"/api/v1/tenants/{tid}/estimates", json=_body(b), headers=h)
    assert r.status_code == 200, r.text
    assert (
        doc.post(
            f"/api/v1/tenants/{tid}/estimates/{r.json()['id']}/issue",
            json={},
            headers=h,
        ).status_code
        == 200
    )
    # Receptionist: read-only here (payment.record does not grant estimates).
    assert recep.get(f"/api/v1/tenants/{tid}/estimates", headers=h).status_code == 200
    assert (
        recep.post(
            f"/api/v1/tenants/{tid}/estimates", json=_body(b), headers=h
        ).status_code
        == 403
    )


def test_estimate_audit_refs_only(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import text

    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="est-api-au")
    doc = login_client(client, email=b["admin"].email)
    tid = b["tenant"].id
    h = tenant_headers(tid)
    created = doc.post(f"/api/v1/tenants/{tid}/estimates", json=_body(b), headers=h)
    assert created.status_code == 200, created.text
    eid = created.json()["id"]
    assert (
        doc.post(
            f"/api/v1/tenants/{tid}/estimates/{eid}/issue", json={}, headers=h
        ).status_code
        == 200
    )
    rows = owner_db.execute(
        text(
            "SELECT action, resource_type, resource_id, reason, before_ref FROM audit_events "
            "WHERE tenant_id = :t AND resource_type = 'estimate'"
        ),
        {"t": str(tid)},
    ).fetchall()
    actions = {r[0] for r in rows}
    assert {"estimate.created", "estimate.issued"} <= actions
    blob = " ".join(str(c) for r in rows for c in r if c is not None)
    assert "200.00" not in blob and "Filling" not in blob
    assert all(r[1] == "estimate" and r[3] is None and r[4] is None for r in rows)


def test_estimate_validation_errors(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="est-api-v")
    doc = login_client(client, email=b["admin"].email)
    tid = b["tenant"].id
    h = tenant_headers(tid)
    bad = _body(b)
    bad["items"] = [{"description": "x", "quantity": "0", "unit_rate": "10.00"}]
    assert (
        doc.post(f"/api/v1/tenants/{tid}/estimates", json=bad, headers=h).status_code
        == 422
    )
    bad2 = _body(b)
    bad2["patient_id"] = str(uuid.uuid4())
    assert (
        doc.post(f"/api/v1/tenants/{tid}/estimates", json=bad2, headers=h).status_code
        == 404
    )
    assert (
        doc.get(
            f"/api/v1/tenants/{tid}/estimates/{uuid.uuid4()}", headers=h
        ).status_code
        == 404
    )
