"""Service catalog API: authorization, CRUD, global visibility, audit."""

from __future__ import annotations

import uuid

from tests.helpers import login_client, provision_clinical, tenant_headers


def _body(code: str) -> dict:
    return {
        "code": code,
        "display": "Consultation",
        "description": "OPD visit",
        "default_rate": "500.00",
        "currency": "INR",
        "hsn_sac": "9983",
        "tax_rate": "18",
    }


def _code(prefix: str = "api") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _membership(owner_db, make_owner_user, tenant, role: str, email: str):  # type: ignore[no-untyped-def]
    from app.modules.tenancy import service as tenancy_service

    user = make_owner_user(email=email)
    tenancy_service.create_membership(
        owner_db,
        user=user,
        tenant=tenant,
        role=tenancy_service.get_seed_role(owner_db, role),
    )
    owner_db.commit()
    return user


def test_admin_crud_and_lifecycle(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="bill-cat-a")
    doc = login_client(client, email=b["admin"].email)
    tid = b["tenant"].id
    h = tenant_headers(tid)
    code = _code()
    created = doc.post(
        f"/api/v1/tenants/{tid}/service-catalog", json=_body(code), headers=h
    )
    assert created.status_code == 200, created.text
    item = created.json()
    assert item["code"] == code
    assert item["default_rate"] == "500.00"
    assert item["is_active"] is True
    listed = doc.get(f"/api/v1/tenants/{tid}/service-catalog", headers=h)
    assert listed.status_code == 200, listed.text
    assert code in [i["code"] for i in listed.json()["items"]]
    got = doc.get(f"/api/v1/tenants/{tid}/service-catalog/{item['id']}", headers=h)
    assert got.status_code == 200, got.text
    assert got.json()["id"] == item["id"]
    patched = doc.patch(
        f"/api/v1/tenants/{tid}/service-catalog/{item['id']}",
        json={"default_rate": "600.00"},
        headers=h,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["default_rate"] == "600.00"
    deact = doc.post(
        f"/api/v1/tenants/{tid}/service-catalog/{item['id']}/deactivate",
        json={},
        headers=h,
    )
    assert deact.status_code == 200, deact.text
    assert deact.json()["is_active"] is False
    act = doc.post(
        f"/api/v1/tenants/{tid}/service-catalog/{item['id']}/activate",
        json={},
        headers=h,
    )
    assert act.status_code == 200, act.text
    assert act.json()["is_active"] is True


def test_role_gates(client, owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="bill-cat-r")
    tid = b["tenant"].id
    h = tenant_headers(tid)
    _membership(
        owner_db, make_owner_user, b["tenant"], "accountant", "acct-cat@example.com"
    )
    _membership(
        owner_db, make_owner_user, b["tenant"], "receptionist", "recep-cat@example.com"
    )
    acct = login_client(client, email="acct-cat@example.com")
    recep = login_client(client, email="recep-cat@example.com")
    doc = login_client(client, email=b["doctor"].email)
    # Accountant configures.
    code = _code()
    assert (
        acct.post(
            f"/api/v1/tenants/{tid}/service-catalog", json=_body(code), headers=h
        ).status_code
        == 200
    )
    # Doctor reads but cannot configure.
    assert (
        doc.get(f"/api/v1/tenants/{tid}/service-catalog", headers=h).status_code == 200
    )
    assert (
        doc.post(
            f"/api/v1/tenants/{tid}/service-catalog", json=_body(_code()), headers=h
        ).status_code
        == 403
    )
    # Receptionist reads but cannot configure.
    assert (
        recep.get(f"/api/v1/tenants/{tid}/service-catalog", headers=h).status_code
        == 200
    )
    assert (
        recep.post(
            f"/api/v1/tenants/{tid}/service-catalog", json=_body(_code()), headers=h
        ).status_code
        == 403
    )


def test_duplicate_unknown_and_tenant_mismatch(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="bill-cat-d")
    tid = b["tenant"].id
    h = tenant_headers(tid)
    doc = login_client(client, email=b["admin"].email)
    code = _code()
    assert (
        doc.post(
            f"/api/v1/tenants/{tid}/service-catalog", json=_body(code), headers=h
        ).status_code
        == 200
    )
    dup = doc.post(
        f"/api/v1/tenants/{tid}/service-catalog", json=_body(code.upper()), headers=h
    )
    assert dup.status_code == 409, dup.text
    assert (
        doc.get(
            f"/api/v1/tenants/{tid}/service-catalog/{uuid.uuid4()}", headers=h
        ).status_code
        == 404
    )
    other = provision_clinical(
        owner_db, make_owner_user, make_tenant, slug="bill-cat-e"
    )
    ho = tenant_headers(other["tenant"].id)
    # Path-tenant mismatch against own session scope is a 404 oracle guard.
    assert (
        doc.get(
            f"/api/v1/tenants/{other['tenant'].id}/service-catalog", headers=h
        ).status_code
        == 404
    )
    assert ho is not None


def test_catalog_is_global_across_tenants(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    a = provision_clinical(owner_db, make_owner_user, make_tenant, slug="bill-cat-g1")
    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="bill-cat-g2")
    da = login_client(client, email=a["admin"].email)
    db_login = login_client(client, email=b["admin"].email)
    code = _code("shared")
    created = da.post(
        f"/api/v1/tenants/{a['tenant'].id}/service-catalog",
        json=_body(code),
        headers=tenant_headers(a["tenant"].id),
    )
    assert created.status_code == 200, created.text
    item_id = created.json()["id"]
    # Second tenant reads the same global entry by ID: no tenant filtering,
    # while authorization (billing.read via tenant_admin) still applies.
    got = db_login.get(
        f"/api/v1/tenants/{b['tenant'].id}/service-catalog/{item_id}",
        headers=tenant_headers(b["tenant"].id),
    )
    assert got.status_code == 200, got.text
    assert got.json()["code"] == code


def test_catalog_audit_is_refs_only(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import text

    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="bill-cat-au")
    doc = login_client(client, email=b["admin"].email)
    tid = b["tenant"].id
    h = tenant_headers(tid)
    marker_rate = "777.77"
    body = _body(_code("audit"))
    body["default_rate"] = marker_rate
    created = doc.post(f"/api/v1/tenants/{tid}/service-catalog", json=body, headers=h)
    assert created.status_code == 200, created.text
    rows = owner_db.execute(
        text(
            "SELECT action, resource_type, resource_id, reason, before_ref FROM audit_events "
            "WHERE tenant_id = :t AND action LIKE 'service_catalog.%'"
        ),
        {"t": str(tid)},
    ).fetchall()
    assert rows, "expected catalog audit entries"
    blob = " ".join(" ".join(str(c) for c in r if c is not None) for r in rows)
    assert marker_rate not in blob
    assert all(r[3] is None and r[4] is None for r in rows)
    assert {r[0] for r in rows} >= {"service_catalog.created"}
    assert all(r[1] == "service_catalog" for r in rows)


def test_catalog_mutation_does_not_touch_snapshots(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    """Regression: future estimate/invoice lines snapshot catalog values.
    Mutating the catalog must leave already-stored snapshot rows untouched."""
    from datetime import datetime, timezone

    from app.modules.billing import models as B
    from app.modules.billing import service_catalog as catalog
    from app.platform import ids

    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="bill-cat-hist")
    base = {
        "tenant_id": b["tenant"].id,
        "location_id": b["location"].id,
        "patient_id": b["patient"].id,
    }
    now = datetime.now(timezone.utc)
    item = catalog.create_service(
        owner_db, code=_code("snap"), display="Snapshot svc", default_rate="500.00"
    )
    est = B.Estimate(
        id=ids.uuid7(),
        status="draft",
        created_at=now,
        updated_at=now,
        **base,
    )
    owner_db.add(est)
    owner_db.flush()
    line = B.EstimateLine(
        id=ids.uuid7(),
        tenant_id=base["tenant_id"],
        estimate_id=est.id,
        service_catalog_id=item.id,
        description=item.display,
        quantity="1.00",
        unit_rate=str(item.default_rate),  # snapshot, not a live link
        line_total=str(item.default_rate),
        created_at=now,
    )
    owner_db.add(line)
    owner_db.flush()
    catalog.update_service(owner_db, item_id=item.id, default_rate="999.00")
    owner_db.expire_all()
    assert str(line.line_total) == "500.00"
    assert str(line.unit_rate) == "500.00"
