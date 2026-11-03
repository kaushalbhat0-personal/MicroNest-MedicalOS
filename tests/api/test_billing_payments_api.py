"""Payment + allocation API (P4.5): recording, allocation, balances,
credit, IDOR, auth matrix, audit, and concurrency."""

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


def _issue_invoice(doc, tid, b, h, rate: str = "100.00"):  # type: ignore[no-untyped-def]
    created = doc.post(
        f"/api/v1/tenants/{tid}/invoices",
        json={
            "patient_id": str(b["patient"].id),
            "location_id": str(b["location"].id),
            "items": [{"description": "Care", "quantity": "1", "unit_rate": rate}],
        },
        headers=h,
    )
    assert created.status_code == 200, created.text
    iid = created.json()["id"]
    issued = doc.post(f"/api/v1/tenants/{tid}/invoices/{iid}/issue", json={}, headers=h)
    assert issued.status_code == 200, issued.text
    return iid


def test_record_and_read_payment(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="pay-api-a")
    doc = login_client(client, email=b["admin"].email)
    tid = b["tenant"].id
    h = tenant_headers(tid)
    created = doc.post(
        f"/api/v1/tenants/{tid}/payments", json=_pay_body(b, "250.00"), headers=h
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["status"] == "recorded"
    assert body["amount"] == "250.00"
    assert body["allocated_amount"] == "0.00"
    assert body["unallocated_amount"] == "250.00"
    assert body["currency"] == "INR"
    assert "provider_data" not in body
    pid = body["id"]
    assert (
        doc.get(f"/api/v1/tenants/{tid}/payments/{pid}", headers=h).status_code == 200
    )
    listed = doc.get(f"/api/v1/tenants/{tid}/payments?limit=1", headers=h)
    assert listed.status_code == 200 and len(listed.json()["items"]) == 1
    # Header idempotency replay returns the same payment.
    replay = doc.post(
        f"/api/v1/tenants/{tid}/payments",
        json=_pay_body(b, "250.00"),
        headers={**h, "Idempotency-Key": "pay-hdr-1"},
    )
    assert replay.status_code == 200
    again = doc.post(
        f"/api/v1/tenants/{tid}/payments",
        json=_pay_body(b, "250.00"),
        headers={**h, "Idempotency-Key": "pay-hdr-1"},
    )
    assert again.status_code == 200 and again.json()["id"] == replay.json()["id"]
    # Same key, divergent amount → 409.
    assert (
        doc.post(
            f"/api/v1/tenants/{tid}/payments",
            json=_pay_body(b, "300.00"),
            headers={**h, "Idempotency-Key": "pay-hdr-1"},
        ).status_code
        == 409
    )
    # Method allowlist and positive-amount guards are 422s.
    assert (
        doc.post(
            f"/api/v1/tenants/{tid}/payments",
            json=_pay_body(b, method="bitcoin"),
            headers=h,
        ).status_code
        == 422
    )
    assert (
        doc.post(
            f"/api/v1/tenants/{tid}/payments", json=_pay_body(b, "0"), headers=h
        ).status_code
        == 422
    )


def test_allocate_and_balances(client, owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="pay-api-b")
    doc = login_client(client, email=b["admin"].email)
    tid = b["tenant"].id
    h = tenant_headers(tid)
    iid = _issue_invoice(doc, tid, b, h, rate="100.00")
    pid = doc.post(
        f"/api/v1/tenants/{tid}/payments", json=_pay_body(b, "150.00"), headers=h
    ).json()["id"]
    allocated = doc.post(
        f"/api/v1/tenants/{tid}/payments/{pid}/allocations",
        json={"allocations": [{"invoice_id": iid, "amount": "100.00"}]},
        headers=h,
    )
    assert allocated.status_code == 200, allocated.text
    assert allocated.json()["items"][0]["amount"] == "100.00"
    invoice = doc.get(f"/api/v1/tenants/{tid}/invoices/{iid}", headers=h).json()
    assert invoice["status"] == "paid"
    assert invoice["allocated_amount"] == "100.00"
    assert invoice["outstanding_amount"] == "0.00"
    payment = doc.get(f"/api/v1/tenants/{tid}/payments/{pid}", headers=h).json()
    assert payment["status"] == "partially_allocated"
    assert payment["unallocated_amount"] == "50.00"
    balance = doc.get(f"/api/v1/tenants/{tid}/invoices/{iid}/balance", headers=h).json()
    assert balance == {
        "invoice_id": iid,
        "status": "paid",
        "grand_total": "100.00",
        "allocated_amount": "100.00",
        "outstanding_amount": "0.00",
    }
    credit = doc.get(
        f"/api/v1/tenants/{tid}/patients/{b['patient'].id}/credit-balance", headers=h
    ).json()
    assert credit == {"patient_id": str(b["patient"].id), "credit_amount": "50.00"}
    # Over-allocation beyond the remainder is rejected, not discarded.
    second = _issue_invoice(doc, tid, b, h, rate="60.00")
    assert (
        doc.post(
            f"/api/v1/tenants/{tid}/payments/{pid}/allocations",
            json={"allocations": [{"invoice_id": second, "amount": "60.00"}]},
            headers=h,
        ).status_code
        == 409
    )


def test_reverse_allocation_api(client, owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="pay-api-r")
    doc = login_client(client, email=b["admin"].email)
    tid = b["tenant"].id
    h = tenant_headers(tid)
    iid = _issue_invoice(doc, tid, b, h, rate="100.00")
    pid = doc.post(
        f"/api/v1/tenants/{tid}/payments", json=_pay_body(b, "100.00"), headers=h
    ).json()["id"]
    alloc_id = doc.post(
        f"/api/v1/tenants/{tid}/payments/{pid}/allocations",
        json={"allocations": [{"invoice_id": iid, "amount": "100.00"}]},
        headers=h,
    ).json()["items"][0]["id"]
    reversed_resp = doc.post(
        f"/api/v1/tenants/{tid}/allocations/{alloc_id}/reverse",
        json={"reason": "wrong invoice"},
        headers=h,
    )
    assert reversed_resp.status_code == 200, reversed_resp.text
    assert reversed_resp.json()["reversal_of_id"] == alloc_id
    invoice = doc.get(f"/api/v1/tenants/{tid}/invoices/{iid}", headers=h).json()
    assert invoice["status"] == "issued" and invoice["outstanding_amount"] == "100.00"
    assert (
        doc.post(
            f"/api/v1/tenants/{tid}/allocations/{alloc_id}/reverse",
            json={"reason": "again"},
            headers=h,
        ).status_code
        == 409
    )


def test_payment_auth_gates(client, owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    from app.modules.tenancy import service as tenancy_service

    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="pay-api-g")
    tid = b["tenant"].id
    h = tenant_headers(tid)
    for role, email in (
        ("accountant", "acct-pay@example.com"),
        ("receptionist", "recep-pay@example.com"),
    ):
        user = make_owner_user(email=email)
        tenancy_service.create_membership(
            owner_db,
            user=user,
            tenant=b["tenant"],
            role=tenancy_service.get_seed_role(owner_db, role),
        )
        owner_db.commit()
    acct = login_client(client, email="acct-pay@example.com")
    recep = login_client(client, email="recep-pay@example.com")
    doc = login_client(client, email=b["doctor"].email)
    admin = login_client(client, email=b["admin"].email)
    iid = _issue_invoice(admin, tid, b, h, rate="100.00")
    # Doctor reads but cannot record or allocate.
    assert doc.get(f"/api/v1/tenants/{tid}/payments", headers=h).status_code == 200
    assert (
        doc.post(
            f"/api/v1/tenants/{tid}/payments", json=_pay_body(b), headers=h
        ).status_code
        == 403
    )
    # Receptionist holds payment.record: record + allocate allowed, issue denied.
    recorded = recep.post(
        f"/api/v1/tenants/{tid}/payments", json=_pay_body(b), headers=h
    )
    assert recorded.status_code == 200, recorded.text
    pid = recorded.json()["id"]
    assert (
        recep.post(
            f"/api/v1/tenants/{tid}/payments/{pid}/allocations",
            json={"allocations": [{"invoice_id": iid, "amount": "100.00"}]},
            headers=h,
        ).status_code
        == 200
    )
    # Accountant: full billing authority over payments.
    second = acct.post(
        f"/api/v1/tenants/{tid}/payments", json=_pay_body(b, "50.00"), headers=h
    )
    assert second.status_code == 200, second.text


def test_idor_and_location_scope(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from app.modules.clinics import service as clinics_service
    from app.modules.tenancy import service as tenancy_service

    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="pay-api-s")
    tid = b["tenant"].id
    h = tenant_headers(tid)
    doc = login_client(client, email=b["admin"].email)
    loc2 = clinics_service.create_location(owner_db, tenant=b["tenant"], name="Annex")
    owner_db.commit()
    scoped_user = make_owner_user(email="scoped-pay@example.com")
    tenancy_service.create_membership(
        owner_db,
        user=scoped_user,
        tenant=b["tenant"],
        role=tenancy_service.get_seed_role(owner_db, "doctor"),
        location_ids=[loc2.id],
    )
    owner_db.commit()
    scoped = login_client(client, email="scoped-pay@example.com")
    pid = doc.post(
        f"/api/v1/tenants/{tid}/payments", json=_pay_body(b), headers=h
    ).json()["id"]
    assert (
        doc.get(f"/api/v1/tenants/{tid}/payments/{pid}", headers=h).status_code == 200
    )
    assert (
        scoped.get(f"/api/v1/tenants/{tid}/payments/{pid}", headers=h).status_code
        == 403
    )
    assert (
        scoped.post(
            f"/api/v1/tenants/{tid}/payments", json=_pay_body(b), headers=h
        ).status_code
        == 403
    )
    other = provision_clinical(owner_db, make_owner_user, make_tenant, slug="pay-api-t")
    ho = tenant_headers(other["tenant"].id)
    other_login = login_client(client, email=other["admin"].email)
    assert (
        other_login.get(
            f"/api/v1/tenants/{other['tenant'].id}/payments/{pid}", headers=ho
        ).status_code
        == 404
    )
    # Cross-patient allocation across the same tenant is rejected.
    from app.modules.patients import service as patients_service

    stranger = patients_service.register_patient(
        owner_db, tenant_id=b["tenant"].id, display_name="Stranger"
    )
    owner_db.commit()
    iid = _issue_invoice(doc, tid, b, h, rate="50.00")
    stranger_pay = doc.post(
        f"/api/v1/tenants/{tid}/payments",
        json=_pay_body(b, patient_id=str(stranger.id)),
        headers=h,
    ).json()["id"]
    assert (
        doc.post(
            f"/api/v1/tenants/{tid}/payments/{stranger_pay}/allocations",
            json={"allocations": [{"invoice_id": iid, "amount": "10.00"}]},
            headers=h,
        ).status_code
        == 422
    )


def test_payment_audit_refs_only(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import text

    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="pay-api-au")
    doc = login_client(client, email=b["admin"].email)
    tid = b["tenant"].id
    h = tenant_headers(tid)
    iid = _issue_invoice(doc, tid, b, h, rate="100.00")
    pid = doc.post(
        f"/api/v1/tenants/{tid}/payments", json=_pay_body(b, "100.00"), headers=h
    ).json()["id"]
    alloc_id = doc.post(
        f"/api/v1/tenants/{tid}/payments/{pid}/allocations",
        json={"allocations": [{"invoice_id": iid, "amount": "100.00"}]},
        headers=h,
    ).json()["items"][0]["id"]
    assert (
        doc.post(
            f"/api/v1/tenants/{tid}/allocations/{alloc_id}/reverse",
            json={"reason": "audit probe"},
            headers=h,
        ).status_code
        == 200
    )
    rows = owner_db.execute(
        text(
            "SELECT action, resource_type, resource_id, reason, before_ref FROM audit_events "
            "WHERE tenant_id = :t AND resource_type IN ('payment', 'allocation')"
        ),
        {"t": str(tid)},
    ).fetchall()
    actions = {r[0] for r in rows}
    assert {"payment.recorded", "payment.allocated", "allocation.reversed"} <= actions
    blob = " ".join(str(c) for r in rows for c in r if c is not None)
    assert "100.00" not in blob
    pay_rows = [r for r in rows if r[1] == "payment"]
    assert all(r[3] is None and r[4] is None for r in pay_rows)


def test_concurrent_final_balance_single_winner(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="pay-race")
    doc = login_client(client, email=b["admin"].email)
    tid = str(b["tenant"].id)
    h = tenant_headers(tid)
    iid = _issue_invoice(doc, b["tenant"].id, b, h, rate="100.00")
    pids = [
        doc.post(
            f"/api/v1/tenants/{tid}/payments", json=_pay_body(b, "100.00"), headers=h
        ).json()["id"]
        for _ in range(2)
    ]
    gate = threading.Barrier(3)
    results: list[int] = []

    def attempt(payment_id: str) -> None:
        c = TestClient(client.app, base_url="http://test")
        resp = c.post(
            "/api/v1/auth/login",
            json={"email": b["admin"].email, "password": "password-12345-abc"},
        )
        assert resp.status_code == 200
        gate.wait(timeout=30)
        r = c.post(
            f"/api/v1/tenants/{tid}/payments/{payment_id}/allocations",
            json={"allocations": [{"invoice_id": iid, "amount": "100.00"}]},
            headers=h,
        )
        results.append(r.status_code)

    threads = [threading.Thread(target=attempt, args=(p,)) for p in pids]
    for t in threads:
        t.start()
    gate.wait(timeout=30)
    for t in threads:
        t.join(timeout=120)
    assert sorted(results) == [200, 409], results
    balance = doc.get(f"/api/v1/tenants/{tid}/invoices/{iid}/balance", headers=h).json()
    assert balance["allocated_amount"] == "100.00"
    assert balance["outstanding_amount"] == "0.00"
    assert balance["status"] == "paid"


def test_concurrent_payment_over_allocation(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="pay-race2")
    doc = login_client(client, email=b["admin"].email)
    tid = str(b["tenant"].id)
    h = tenant_headers(tid)
    first = _issue_invoice(doc, b["tenant"].id, b, h, rate="100.00")
    second = _issue_invoice(doc, b["tenant"].id, b, h, rate="100.00")
    pid = doc.post(
        f"/api/v1/tenants/{tid}/payments", json=_pay_body(b, "100.00"), headers=h
    ).json()["id"]
    gate = threading.Barrier(3)
    results: list[int] = []

    def attempt(invoice_id: str) -> None:
        c = TestClient(client.app, base_url="http://test")
        resp = c.post(
            "/api/v1/auth/login",
            json={"email": b["admin"].email, "password": "password-12345-abc"},
        )
        assert resp.status_code == 200
        gate.wait(timeout=30)
        r = c.post(
            f"/api/v1/tenants/{tid}/payments/{pid}/allocations",
            json={"allocations": [{"invoice_id": invoice_id, "amount": "100.00"}]},
            headers=h,
        )
        results.append(r.status_code)

    threads = [threading.Thread(target=attempt, args=(i,)) for i in (first, second)]
    for t in threads:
        t.start()
    gate.wait(timeout=30)
    for t in threads:
        t.join(timeout=120)
    assert sorted(results) == [200, 409], results
    payment = doc.get(f"/api/v1/tenants/{tid}/payments/{pid}", headers=h).json()
    assert payment["allocated_amount"] == "100.00"
    assert payment["unallocated_amount"] == "0.00"
