"""Invoice API (P4.4): CRUD, money strings, lifecycle, conversion, IDOR, audit."""

from __future__ import annotations

import threading
import uuid
from decimal import Decimal

from fastapi.testclient import TestClient

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


def _issued_estimate_id(doc, tid, b, h, items):  # type: ignore[no-untyped-def]
    created = doc.post(
        f"/api/v1/tenants/{tid}/estimates",
        json={
            "patient_id": str(b["patient"].id),
            "location_id": str(b["location"].id),
            "items": items,
        },
        headers=h,
    )
    assert created.status_code == 200, created.text
    eid = created.json()["id"]
    issued = doc.post(
        f"/api/v1/tenants/{tid}/estimates/{eid}/issue", json={}, headers=h
    )
    assert issued.status_code == 200, issued.text
    return eid


def test_crud_and_money_strings(client, owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="inv-api-a")
    doc = login_client(client, email=b["admin"].email)
    tid = b["tenant"].id
    h = tenant_headers(tid)
    created = doc.post(f"/api/v1/tenants/{tid}/invoices", json=_body(b), headers=h)
    assert created.status_code == 200, created.text
    item = created.json()
    assert item["status"] == "draft" and item["doc_number"] is None
    assert item["grand_total"] == "472.00"
    assert Decimal(item["grand_total"]) == Decimal("472.00")
    assert "e" not in item["grand_total"].lower()
    assert item["lines"][0]["source_estimate_line_id"] is None
    iid = item["id"]
    assert (
        doc.get(f"/api/v1/tenants/{tid}/invoices/{iid}", headers=h).status_code == 200
    )
    patched = doc.patch(
        f"/api/v1/tenants/{tid}/invoices/{iid}", json={"notes": "pay soon"}, headers=h
    )
    assert patched.status_code == 200 and patched.json()["notes"] == "pay soon"
    listed = doc.get(f"/api/v1/tenants/{tid}/invoices?limit=1", headers=h)
    assert listed.status_code == 200 and len(listed.json()["items"]) == 1
    assert listed.json()["next_cursor"] is None
    # Empty draft cannot issue.
    bare = doc.post(
        f"/api/v1/tenants/{tid}/invoices",
        json=_body(b, items=[]),
        headers=h,
    )
    assert bare.status_code == 200, bare.text
    assert (
        doc.post(
            f"/api/v1/tenants/{bare.json()['id']}/issue", json={}, headers=h
        ).status_code
        == 404  # wrong path shape: invoice id must be under invoices
    )
    assert (
        doc.post(
            f"/api/v1/tenants/{tid}/invoices/{bare.json()['id']}/issue",
            json={},
            headers=h,
        ).status_code
        == 422
    )


def test_issue_freeze_and_void(client, owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="inv-api-f")
    doc = login_client(client, email=b["admin"].email)
    tid = b["tenant"].id
    h = tenant_headers(tid)
    iid = doc.post(f"/api/v1/tenants/{tid}/invoices", json=_body(b), headers=h).json()[
        "id"
    ]
    issued = doc.post(f"/api/v1/tenants/{tid}/invoices/{iid}/issue", json={}, headers=h)
    assert issued.status_code == 200, issued.text
    assert issued.json()["status"] == "issued"
    assert issued.json()["doc_number"] == 1
    assert issued.json()["financial_year"] is not None
    # Re-issue is a no-op: same number.
    assert (
        doc.post(
            f"/api/v1/tenants/{tid}/invoices/{iid}/issue", json={}, headers=h
        ).json()["doc_number"]
        == 1
    )
    # Frozen: every draft writer rejects the issued invoice.
    assert (
        doc.patch(
            f"/api/v1/tenants/{tid}/invoices/{iid}", json={"notes": "x"}, headers=h
        ).status_code
        == 409
    )
    assert (
        doc.post(
            f"/api/v1/tenants/{tid}/invoices/{iid}/lines",
            json={"description": "late", "quantity": "1", "unit_rate": "10.00"},
            headers=h,
        ).status_code
        == 409
    )
    line_id = issued.json()["lines"][0]["id"]
    assert (
        doc.patch(
            f"/api/v1/tenants/{tid}/invoice-lines/{line_id}",
            json={"quantity": "9"},
            headers=h,
        ).status_code
        == 409
    )
    assert (
        doc.delete(
            f"/api/v1/tenants/{tid}/invoice-lines/{line_id}", headers=h
        ).status_code
        == 409
    )
    # Issued void without a reason is rejected (RFC-7807 envelope).
    bad = doc.post(f"/api/v1/tenants/{tid}/invoices/{iid}/void", json={}, headers=h)
    assert bad.status_code == 422
    assert set(bad.json()) >= {"type", "title", "status", "detail", "trace_id"}
    voided = doc.post(
        f"/api/v1/tenants/{tid}/invoices/{iid}/void",
        json={"reason": "duplicate billing"},
        headers=h,
    )
    assert voided.status_code == 200, voided.text
    assert voided.json()["status"] == "voided"


def test_convert_estimate_full_and_partial(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="inv-api-c")
    doc = login_client(client, email=b["admin"].email)
    tid = b["tenant"].id
    h = tenant_headers(tid)
    eid = _issued_estimate_id(
        doc,
        tid,
        b,
        h,
        items=[
            {"description": "A", "quantity": "1", "unit_rate": "100.00"},
            {"description": "B", "quantity": "1", "unit_rate": "200.00"},
        ],
    )
    estimate = doc.get(f"/api/v1/tenants/{tid}/estimates/{eid}", headers=h).json()
    line_a = next(line for line in estimate["lines"] if line["description"] == "A")
    converted = doc.post(
        f"/api/v1/tenants/{tid}/estimates/{eid}/convert",
        json={"line_ids": [line_a["id"]]},
        headers={**h, "Idempotency-Key": "conv-api-1"},
    )
    assert converted.status_code == 200, converted.text
    body = converted.json()
    assert body["source_estimate_id"] == eid
    assert body["grand_total"] == "100.00"
    assert body["lines"][0]["source_estimate_line_id"] == line_a["id"]
    # Header replay returns the same invoice.
    replay = doc.post(
        f"/api/v1/tenants/{tid}/estimates/{eid}/convert",
        json={"line_ids": [line_a["id"]]},
        headers={**h, "Idempotency-Key": "conv-api-1"},
    )
    assert replay.status_code == 200 and replay.json()["id"] == body["id"]
    # Same key, divergent lines → 409.
    line_b = next(line for line in estimate["lines"] if line["description"] == "B")
    assert (
        doc.post(
            f"/api/v1/tenants/{tid}/estimates/{eid}/convert",
            json={"line_ids": [line_b["id"]]},
            headers={**h, "Idempotency-Key": "conv-api-1"},
        ).status_code
        == 409
    )
    # Partial keeps the estimate issued; converting the rest completes it.
    assert (
        doc.get(f"/api/v1/tenants/{tid}/estimates/{eid}", headers=h).json()["status"]
        == "issued"
    )
    rest = doc.post(
        f"/api/v1/tenants/{tid}/estimates/{eid}/convert",
        json={"line_ids": [line_b["id"]]},
        headers=h,
    )
    assert rest.status_code == 200, rest.text
    assert (
        doc.get(f"/api/v1/tenants/{tid}/estimates/{eid}", headers=h).json()["status"]
        == "converted"
    )
    # Already-converted line → 409.
    assert (
        doc.post(
            f"/api/v1/tenants/{tid}/estimates/{eid}/convert",
            json={"line_ids": [line_a["id"]]},
            headers=h,
        ).status_code
        == 409
    )


def test_idor_and_location_scope(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from app.modules.clinics import service as clinics_service

    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="inv-api-s")
    tid = b["tenant"].id
    h = tenant_headers(tid)
    doc = login_client(client, email=b["admin"].email)
    loc2 = clinics_service.create_location(owner_db, tenant=b["tenant"], name="Annex")
    owner_db.commit()
    from app.modules.tenancy import service as tenancy_service

    scoped_user = make_owner_user(email="scoped-inv@example.com")
    tenancy_service.create_membership(
        owner_db,
        user=scoped_user,
        tenant=b["tenant"],
        role=tenancy_service.get_seed_role(owner_db, "doctor"),
        location_ids=[loc2.id],
    )
    owner_db.commit()
    scoped = login_client(client, email="scoped-inv@example.com")
    iid = doc.post(f"/api/v1/tenants/{tid}/invoices", json=_body(b), headers=h).json()[
        "id"
    ]
    assert (
        doc.get(f"/api/v1/tenants/{tid}/invoices/{iid}", headers=h).status_code == 200
    )
    assert (
        scoped.get(f"/api/v1/tenants/{tid}/invoices/{iid}", headers=h).status_code
        == 403
    )
    assert (
        scoped.post(
            f"/api/v1/tenants/{tid}/invoices", json=_body(b), headers=h
        ).status_code
        == 403
    )
    # Cross-tenant probe → 404 oracle.
    other = provision_clinical(owner_db, make_owner_user, make_tenant, slug="inv-api-t")
    ho = tenant_headers(other["tenant"].id)
    other_login = login_client(client, email=other["admin"].email)
    assert (
        other_login.get(
            f"/api/v1/tenants/{other['tenant'].id}/invoices/{iid}", headers=ho
        ).status_code
        == 404
    )
    # Cross-tenant estimate conversion → 404.
    eid = _issued_estimate_id(
        other_login,
        other["tenant"].id,
        other,
        ho,
        items=[{"description": "A", "quantity": "1", "unit_rate": "10.00"}],
    )
    assert (
        doc.post(
            f"/api/v1/tenants/{tid}/estimates/{eid}/convert", json={}, headers=h
        ).status_code
        == 404
    )


def test_invoice_auth_gates(client, owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    from app.modules.tenancy import service as tenancy_service

    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="inv-api-g")
    tid = b["tenant"].id
    h = tenant_headers(tid)
    for role, email in (
        ("accountant", "acct-inv@example.com"),
        ("receptionist", "recep-inv@example.com"),
    ):
        user = make_owner_user(email=email)
        tenancy_service.create_membership(
            owner_db,
            user=user,
            tenant=b["tenant"],
            role=tenancy_service.get_seed_role(owner_db, role),
        )
        owner_db.commit()
    acct = login_client(client, email="acct-inv@example.com")
    recep = login_client(client, email="recep-inv@example.com")
    doc = login_client(client, email=b["doctor"].email)
    admin = login_client(client, email=b["admin"].email)
    # Doctor: billing.create covers drafts + conversion, never issue.
    created = doc.post(f"/api/v1/tenants/{tid}/invoices", json=_body(b), headers=h)
    assert created.status_code == 200, created.text
    iid = created.json()["id"]
    assert (
        doc.post(
            f"/api/v1/tenants/{tid}/invoices/{iid}/issue", json={}, headers=h
        ).status_code
        == 403
    )
    # Receptionist: read-only here (payment.record grants no invoice writes).
    assert recep.get(f"/api/v1/tenants/{tid}/invoices", headers=h).status_code == 200
    assert (
        recep.post(
            f"/api/v1/tenants/{tid}/invoices", json=_body(b), headers=h
        ).status_code
        == 403
    )
    assert (
        recep.post(
            f"/api/v1/tenants/{tid}/invoices/{iid}/void",
            json={"reason": "nope nope"},
            headers=h,
        ).status_code
        == 403
    )
    # Accountant: full billing authority incl. issue/void.
    issued = acct.post(
        f"/api/v1/tenants/{tid}/invoices/{iid}/issue", json={}, headers=h
    )
    assert issued.status_code == 200, issued.text
    assert (
        acct.post(
            f"/api/v1/tenants/{tid}/invoices/{iid}/void",
            json={"reason": "entered in error"},
            headers=h,
        ).status_code
        == 200
    )
    # Tenant admin retains full control.
    admin_created = admin.post(
        f"/api/v1/tenants/{tid}/invoices", json=_body(b), headers=h
    )
    assert admin_created.status_code == 200


def test_invoice_audit_refs_only(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import text

    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="inv-api-au")
    doc = login_client(client, email=b["admin"].email)
    tid = b["tenant"].id
    h = tenant_headers(tid)
    iid = doc.post(f"/api/v1/tenants/{tid}/invoices", json=_body(b), headers=h).json()[
        "id"
    ]
    assert (
        doc.post(
            f"/api/v1/tenants/{tid}/invoices/{iid}/issue", json={}, headers=h
        ).status_code
        == 200
    )
    assert (
        doc.post(
            f"/api/v1/tenants/{tid}/invoices/{iid}/void",
            json={"reason": "audit probe"},
            headers=h,
        ).status_code
        == 200
    )
    rows = owner_db.execute(
        text(
            "SELECT action, resource_type, resource_id, reason, before_ref FROM audit_events "
            "WHERE tenant_id = :t AND resource_type = 'invoice'"
        ),
        {"t": str(tid)},
    ).fetchall()
    actions = {r[0] for r in rows}
    assert {"invoice.created", "invoice.issued", "invoice.voided"} <= actions
    blob = " ".join(str(c) for r in rows for c in r if c is not None)
    assert "200.00" not in blob and "Filling" not in blob
    assert all(r[1] == "invoice" and r[3] is None and r[4] is None for r in rows)


def test_concurrent_conversion_single_winner(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="inv-race")
    doc = login_client(client, email=b["admin"].email)
    tid = str(b["tenant"].id)
    h = tenant_headers(tid)
    eid = _issued_estimate_id(
        doc,
        b["tenant"].id,
        b,
        h,
        items=[{"description": "A", "quantity": "1", "unit_rate": "100.00"}],
    )
    gate = threading.Barrier(3)
    results: list[int] = []

    def attempt() -> None:
        c = TestClient(client.app, base_url="http://test")
        resp = c.post(
            "/api/v1/auth/login",
            json={"email": b["admin"].email, "password": "password-12345-abc"},
        )
        assert resp.status_code == 200
        gate.wait(timeout=30)
        r = c.post(
            f"/api/v1/tenants/{tid}/estimates/{eid}/convert",
            json={},
            headers={**h, "Idempotency-Key": f"race-{uuid.uuid4().hex[:8]}"},
        )
        results.append(r.status_code)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for t in threads:
        t.start()
    gate.wait(timeout=30)
    for t in threads:
        t.join(timeout=120)
    assert sorted(results) == [200, 409], results
    listed = doc.get(f"/api/v1/tenants/{tid}/invoices", headers=h).json()
    assert len(listed["items"]) == 1


def test_concurrent_issue_distinct_numbers(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(
        owner_db, make_owner_user, make_tenant, slug="inv-issue-race"
    )
    doc = login_client(client, email=b["admin"].email)
    tid = str(b["tenant"].id)
    h = tenant_headers(tid)
    ids = [
        doc.post(f"/api/v1/tenants/{tid}/invoices", json=_body(b), headers=h).json()[
            "id"
        ]
        for _ in range(2)
    ]
    gate = threading.Barrier(3)
    numbers: list[int] = []

    def attempt(invoice_id: str) -> None:
        c = TestClient(client.app, base_url="http://test")
        resp = c.post(
            "/api/v1/auth/login",
            json={"email": b["admin"].email, "password": "password-12345-abc"},
        )
        assert resp.status_code == 200
        gate.wait(timeout=30)
        r = c.post(
            f"/api/v1/tenants/{tid}/invoices/{invoice_id}/issue", json={}, headers=h
        )
        assert r.status_code == 200, r.text
        numbers.append(r.json()["doc_number"])

    threads = [threading.Thread(target=attempt, args=(i,)) for i in ids]
    for t in threads:
        t.start()
    gate.wait(timeout=30)
    for t in threads:
        t.join(timeout=120)
    assert sorted(numbers) == [1, 2], numbers
