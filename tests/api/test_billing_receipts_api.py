"""Receipt API (P4.7): evidence-only endpoints, auth matrix, IDOR, audit."""

from __future__ import annotations

import threading

from fastapi.testclient import TestClient

from tests.helpers import login_client, provision_clinical, tenant_headers


def _pay_body(b, amount: str = "100.00", **kw):  # type: ignore[no-untyped-def]
    args = {
        "patient_id": str(b["patient"].id),
        "location_id": str(b["location"].id),
        "method": "cash",
        "amount": amount,
    }
    args.update(kw)
    return args


def _record_payment(doc, tid, b, h, amount: str = "100.00"):  # type: ignore[no-untyped-def]
    recorded = doc.post(
        f"/api/v1/tenants/{tid}/payments", json=_pay_body(b, amount), headers=h
    )
    assert recorded.status_code == 200, recorded.text
    return recorded.json()["id"]


def _create_receipt(doc, tid, pid, h, key: str | None = None):  # type: ignore[no-untyped-def]
    headers = dict(h)
    if key:
        headers["Idempotency-Key"] = key
    return doc.post(
        f"/api/v1/tenants/{tid}/payments/{pid}/receipt", json={}, headers=headers
    )


def test_create_and_read_receipt(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="rcpt-api-a")
    doc = login_client(client, email=b["admin"].email)
    tid = b["tenant"].id
    h = tenant_headers(tid)
    pid = _record_payment(doc, tid, b, h, amount="250.00")
    created = _create_receipt(doc, tid, pid, h)
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["payment_id"] == pid
    assert body["patient_id"] == str(b["patient"].id)
    assert body["location_id"] == str(b["location"].id)
    assert body["amount"] == "250.00"
    assert body["currency"] == "INR"
    assert body["financial_year"] is not None
    assert body["doc_number"] == 1
    assert "provider_data" not in body
    # Second receipt for the same payment is a 409, even with a fresh key.
    assert _create_receipt(doc, tid, pid, h).status_code == 409
    assert _create_receipt(doc, tid, pid, h, key="fresh-key").status_code == 409
    # Read back by id.
    rid = body["id"]
    fetched = doc.get(f"/api/v1/tenants/{tid}/receipts/{rid}", headers=h)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json() == body
    # Error envelope is RFC-7807.
    missing = doc.get(
        f"/api/v1/tenants/{tid}/receipts/00000000-0000-0000-0000-000000000000",
        headers=h,
    )
    assert missing.status_code == 404
    for key in ("type", "title", "status", "detail", "trace_id"):
        assert key in missing.json(), key


def test_receipt_idempotency_header(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="rcpt-api-k")
    doc = login_client(client, email=b["admin"].email)
    tid = b["tenant"].id
    h = tenant_headers(tid)
    pid = _record_payment(doc, tid, b, h, amount="100.00")
    first = _create_receipt(doc, tid, pid, h, key="rcpt-hdr-1")
    assert first.status_code == 200, first.text
    replay = _create_receipt(doc, tid, pid, h, key="rcpt-hdr-1")
    assert replay.status_code == 200 and replay.json()["id"] == first.json()["id"]
    assert replay.json()["doc_number"] == first.json()["doc_number"]
    other = _record_payment(doc, tid, b, h, amount="100.00")
    assert _create_receipt(doc, tid, other, h, key="rcpt-hdr-1").status_code == 409


def test_receipt_auth_gates(client, owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    from app.modules.tenancy import service as tenancy_service

    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="rcpt-api-g")
    tid = b["tenant"].id
    h = tenant_headers(tid)
    for role, email in (
        ("accountant", "acct-rcpt@example.com"),
        ("receptionist", "recep-rcpt@example.com"),
        ("nurse", "nurse-rcpt@example.com"),
    ):
        user = make_owner_user(email=email)
        tenancy_service.create_membership(
            owner_db,
            user=user,
            tenant=b["tenant"],
            role=tenancy_service.get_seed_role(owner_db, role),
        )
        owner_db.commit()
    acct = login_client(client, email="acct-rcpt@example.com")
    recep = login_client(client, email="recep-rcpt@example.com")
    nurse = login_client(client, email="nurse-rcpt@example.com")
    doc = login_client(client, email=b["doctor"].email)
    admin = login_client(client, email=b["admin"].email)
    pid = _record_payment(admin, tid, b, h, amount="100.00")
    # Doctor holds billing.read/create but not payment.record: read yes, create no.
    assert doc.get(
        f"/api/v1/tenants/{tid}/payments/{pid}/receipt", headers=h
    ).status_code in (404, 405)
    assert _create_receipt(doc, tid, pid, h).status_code == 403
    # Receptionist holds payment.record: create allowed.
    recep_pid = _record_payment(recep, tid, b, h, amount="60.00")
    assert _create_receipt(recep, tid, recep_pid, h).status_code == 200
    # Accountant holds full billing: create + read allowed.
    acct_pid = _record_payment(acct, tid, b, h, amount="70.00")
    created = _create_receipt(acct, tid, acct_pid, h)
    assert created.status_code == 200, created.text
    assert (
        acct.get(
            f"/api/v1/tenants/{tid}/receipts/{created.json()['id']}", headers=h
        ).status_code
        == 200
    )
    assert (
        doc.get(
            f"/api/v1/tenants/{tid}/receipts/{created.json()['id']}", headers=h
        ).status_code
        == 200
    )
    # Nurse holds no billing permission: both denied.
    assert _create_receipt(nurse, tid, acct_pid, h).status_code == 403
    assert (
        nurse.get(
            f"/api/v1/tenants/{tid}/receipts/{created.json()['id']}", headers=h
        ).status_code
        == 403
    )


def test_idor_and_location_scope(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from app.modules.clinics import service as clinics_service
    from app.modules.tenancy import service as tenancy_service

    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="rcpt-api-s")
    tid = b["tenant"].id
    h = tenant_headers(tid)
    doc = login_client(client, email=b["admin"].email)
    loc2 = clinics_service.create_location(owner_db, tenant=b["tenant"], name="Annex")
    owner_db.commit()
    scoped_user = make_owner_user(email="scoped-rcpt@example.com")
    tenancy_service.create_membership(
        owner_db,
        user=scoped_user,
        tenant=b["tenant"],
        role=tenancy_service.get_seed_role(owner_db, "doctor"),
        location_ids=[loc2.id],
    )
    owner_db.commit()
    scoped = login_client(client, email="scoped-rcpt@example.com")
    pid = _record_payment(doc, tid, b, h, amount="80.00")
    rid = _create_receipt(doc, tid, pid, h).json()["id"]
    assert (
        doc.get(f"/api/v1/tenants/{tid}/receipts/{rid}", headers=h).status_code == 200
    )
    assert (
        scoped.get(f"/api/v1/tenants/{tid}/receipts/{rid}", headers=h).status_code
        == 403
    )
    assert _create_receipt(scoped, tid, pid, h).status_code == 403
    other = provision_clinical(
        owner_db, make_owner_user, make_tenant, slug="rcpt-api-t"
    )
    ho = tenant_headers(other["tenant"].id)
    other_login = login_client(client, email=other["admin"].email)
    assert (
        other_login.get(
            f"/api/v1/tenants/{other['tenant'].id}/receipts/{rid}", headers=ho
        ).status_code
        == 404
    )
    assert (
        other_login.post(
            f"/api/v1/tenants/{other['tenant'].id}/payments/{pid}/receipt",
            json={},
            headers=ho,
        ).status_code
        == 404
    )
    # Receipt pins the payment's patient: no cross-patient evidence swap.
    from app.modules.patients import service as patients_service

    stranger = patients_service.register_patient(
        owner_db, tenant_id=b["tenant"].id, display_name="Stranger"
    )
    owner_db.commit()
    stranger_pid = doc.post(
        f"/api/v1/tenants/{tid}/payments",
        json=_pay_body(b, patient_id=str(stranger.id)),
        headers=h,
    ).json()["id"]
    stranger_receipt = _create_receipt(doc, tid, stranger_pid, h).json()
    assert stranger_receipt["patient_id"] == str(stranger.id)
    assert stranger_receipt["patient_id"] != str(b["patient"].id)


def test_receipt_audit_refs_only(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import text

    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="rcpt-api-au")
    doc = login_client(client, email=b["admin"].email)
    tid = b["tenant"].id
    h = tenant_headers(tid)
    pid = _record_payment(doc, tid, b, h, amount="100.00")
    rid = _create_receipt(doc, tid, pid, h).json()["id"]
    rows = owner_db.execute(
        text(
            "SELECT action, resource_type, resource_id, reason, before_ref FROM audit_events "
            "WHERE tenant_id = :t AND resource_type = 'receipt'"
        ),
        {"t": str(tid)},
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "receipt.issued"
    assert rows[0][2] == rid
    blob = " ".join(str(c) for r in rows for c in r if c is not None)
    assert "100.00" not in blob
    assert all(r[3] is None and r[4] is None for r in rows)


def test_concurrent_receipt_single_winner(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="rcpt-race")
    doc = login_client(client, email=b["admin"].email)
    tid = str(b["tenant"].id)
    h = tenant_headers(tid)
    pid = _record_payment(doc, b["tenant"].id, b, h, amount="100.00")
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
            f"/api/v1/tenants/{tid}/payments/{pid}/receipt",
            json={},
            headers=h,
        )
        results.append(r.status_code)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for t in threads:
        t.start()
    gate.wait(timeout=30)
    for t in threads:
        t.join(timeout=120)
    assert sorted(results) == [200, 409], results
