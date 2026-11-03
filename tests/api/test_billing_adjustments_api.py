"""Refund + credit note API (P4.6): correction flows, auth matrix, IDOR,
audit, and concurrency."""

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


def _record_payment(doc, tid, b, h, amount: str = "100.00"):  # type: ignore[no-untyped-def]
    recorded = doc.post(
        f"/api/v1/tenants/{tid}/payments", json=_pay_body(b, amount), headers=h
    )
    assert recorded.status_code == 200, recorded.text
    return recorded.json()["id"]


def _allocate(doc, tid, pid, iid, amount: str, h):  # type: ignore[no-untyped-def]
    allocated = doc.post(
        f"/api/v1/tenants/{tid}/payments/{pid}/allocations",
        json={"allocations": [{"invoice_id": iid, "amount": amount}]},
        headers=h,
    )
    assert allocated.status_code == 200, allocated.text
    return allocated.json()["items"][0]["id"]


def _issue_note(doc, tid, iid, h, amount: str = "30.00"):  # type: ignore[no-untyped-def]
    draft = doc.post(
        f"/api/v1/tenants/{tid}/invoices/{iid}/credit-notes",
        json={"amount": amount, "reason": "billing error"},
        headers=h,
    )
    assert draft.status_code == 200, draft.text
    assert draft.json()["status"] == "draft" and draft.json()["doc_number"] is None
    issued = doc.post(
        f"/api/v1/tenants/{tid}/credit-notes/{draft.json()['id']}/issue",
        json={},
        headers=h,
    )
    assert issued.status_code == 200, issued.text
    assert issued.json()["status"] == "issued"
    assert issued.json()["doc_number"] is not None
    return issued.json()


def test_refund_flow_and_balance(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="ref-api-a")
    doc = login_client(client, email=b["admin"].email)
    tid = b["tenant"].id
    h = tenant_headers(tid)
    iid = _issue_invoice(doc, tid, b, h, rate="200.00")
    pid = _record_payment(doc, tid, b, h, amount="200.00")
    _allocate(doc, tid, pid, iid, "200.00", h)
    assert (
        doc.get(f"/api/v1/tenants/{tid}/invoices/{iid}", headers=h).json()["status"]
        == "paid"
    )
    refunded = doc.post(
        f"/api/v1/tenants/{tid}/payments/{pid}/refunds",
        json={"amount": "200.00", "reason": "service not rendered"},
        headers=h,
    )
    assert refunded.status_code == 200, refunded.text
    body = refunded.json()
    assert body["status"] == "issued" and body["reason"] == "service not rendered"
    assert "provider_data" not in body
    # Money-return tracks on the payment; allocation truth moved first.
    payment = doc.get(f"/api/v1/tenants/{tid}/payments/{pid}", headers=h).json()
    assert payment["status"] == "refunded"
    assert payment["unallocated_amount"] == "0.00"
    invoice = doc.get(f"/api/v1/tenants/{tid}/invoices/{iid}", headers=h).json()
    assert invoice["status"] == "issued"
    assert invoice["outstanding_amount"] == "200.00"
    assert (
        doc.get(f"/api/v1/tenants/{tid}/refunds/{body['id']}", headers=h).status_code
        == 200
    )
    listed = doc.get(f"/api/v1/tenants/{tid}/payments/{pid}/refunds", headers=h).json()
    assert len(listed["items"]) == 1
    # Over-refund rejected (never clamped).
    assert (
        doc.post(
            f"/api/v1/tenants/{tid}/payments/{pid}/refunds",
            json={"amount": "0.01", "reason": "over remainder"},
            headers=h,
        ).status_code
        == 422
    )


def test_credit_note_flow_and_balance(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="cn-api-a")
    doc = login_client(client, email=b["admin"].email)
    tid = b["tenant"].id
    h = tenant_headers(tid)
    iid = _issue_invoice(doc, tid, b, h, rate="200.00")
    note = _issue_note(doc, tid, iid, h, amount="50.00")
    assert note["financial_year"] is not None
    invoice = doc.get(f"/api/v1/tenants/{tid}/invoices/{iid}", headers=h).json()
    assert invoice["outstanding_amount"] == "150.00"
    assert invoice["status"] == "issued"
    assert (
        doc.get(
            f"/api/v1/tenants/{tid}/credit-notes/{note['id']}", headers=h
        ).status_code
        == 200
    )
    listed = doc.get(
        f"/api/v1/tenants/{tid}/invoices/{iid}/credit-notes", headers=h
    ).json()
    assert len(listed["items"]) == 1
    # Over-credit rejected.
    assert (
        doc.post(
            f"/api/v1/tenants/{tid}/invoices/{iid}/credit-notes",
            json={"amount": "200.00", "reason": "excess"},
            headers=h,
        ).status_code
        == 422
    )
    # Issued notes cannot be voided; drafts can.
    assert (
        doc.post(
            f"/api/v1/tenants/{tid}/credit-notes/{note['id']}/void",
            json={"reason": "oops"},
            headers=h,
        ).status_code
        == 409
    )
    draft = doc.post(
        f"/api/v1/tenants/{tid}/invoices/{iid}/credit-notes",
        json={"amount": "10.00", "reason": "drafted"},
        headers=h,
    ).json()
    voided = doc.post(
        f"/api/v1/tenants/{tid}/credit-notes/{draft['id']}/void",
        json={},
        headers=h,
    )
    assert voided.status_code == 200 and voided.json()["status"] == "voided"


def test_refund_credit_auth_gates(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from app.modules.tenancy import service as tenancy_service

    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="ref-api-g")
    tid = b["tenant"].id
    h = tenant_headers(tid)
    for role, email in (
        ("accountant", "acct-ref@example.com"),
        ("receptionist", "recep-ref@example.com"),
    ):
        user = make_owner_user(email=email)
        tenancy_service.create_membership(
            owner_db,
            user=user,
            tenant=b["tenant"],
            role=tenancy_service.get_seed_role(owner_db, role),
        )
        owner_db.commit()
    acct = login_client(client, email="acct-ref@example.com")
    recep = login_client(client, email="recep-ref@example.com")
    doc = login_client(client, email=b["doctor"].email)
    admin = login_client(client, email=b["admin"].email)
    iid = _issue_invoice(admin, tid, b, h, rate="100.00")
    pid = _record_payment(admin, tid, b, h, amount="100.00")
    payload = {"amount": "10.00", "reason": "gate probe"}
    # Doctor and receptionist hold no billing.refund: both denied everywhere.
    for user in (doc, recep):
        assert (
            user.post(
                f"/api/v1/tenants/{tid}/payments/{pid}/refunds", json=payload, headers=h
            ).status_code
            == 403
        )
        assert (
            user.post(
                f"/api/v1/tenants/{tid}/invoices/{iid}/credit-notes",
                json=payload,
                headers=h,
            ).status_code
            == 403
        )
    assert (
        user.get(f"/api/v1/tenants/{tid}/payments/{pid}/refunds", headers=h).status_code
        == 200
    )
    # Accountant holds the financial-adjustment authority.
    assert (
        acct.post(
            f"/api/v1/tenants/{tid}/payments/{pid}/refunds", json=payload, headers=h
        ).status_code
        == 200
    )
    assert (
        acct.post(
            f"/api/v1/tenants/{tid}/invoices/{iid}/credit-notes",
            json=payload,
            headers=h,
        ).status_code
        == 200
    )


def test_idor_and_location_scope(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from app.modules.clinics import service as clinics_service
    from app.modules.tenancy import service as tenancy_service

    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="ref-api-s")
    tid = b["tenant"].id
    h = tenant_headers(tid)
    doc = login_client(client, email=b["admin"].email)
    loc2 = clinics_service.create_location(owner_db, tenant=b["tenant"], name="Annex")
    owner_db.commit()
    scoped_user = make_owner_user(email="scoped-ref@example.com")
    tenancy_service.create_membership(
        owner_db,
        user=scoped_user,
        tenant=b["tenant"],
        role=tenancy_service.get_seed_role(owner_db, "doctor"),
        location_ids=[loc2.id],
    )
    owner_db.commit()
    scoped = login_client(client, email="scoped-ref@example.com")
    _issue_invoice(doc, tid, b, h, rate="50.00")
    pid = _record_payment(doc, tid, b, h, amount="50.00")
    rid = doc.post(
        f"/api/v1/tenants/{tid}/payments/{pid}/refunds",
        json={"amount": "50.00", "reason": "scope probe"},
        headers=h,
    ).json()["id"]
    assert doc.get(f"/api/v1/tenants/{tid}/refunds/{rid}", headers=h).status_code == 200
    assert (
        scoped.get(f"/api/v1/tenants/{tid}/refunds/{rid}", headers=h).status_code == 403
    )
    assert (
        scoped.post(
            f"/api/v1/tenants/{tid}/payments/{pid}/refunds",
            json={"amount": "1.00", "reason": "nope nope"},
            headers=h,
        ).status_code
        == 403
    )
    other = provision_clinical(owner_db, make_owner_user, make_tenant, slug="ref-api-t")
    ho = tenant_headers(other["tenant"].id)
    other_login = login_client(client, email=other["admin"].email)
    assert (
        other_login.get(
            f"/api/v1/tenants/{other['tenant'].id}/refunds/{rid}", headers=ho
        ).status_code
        == 404
    )


def test_audit_refs_only(client, owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import text

    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="ref-api-au")
    doc = login_client(client, email=b["admin"].email)
    tid = b["tenant"].id
    h = tenant_headers(tid)
    iid = _issue_invoice(doc, tid, b, h, rate="100.00")
    pid = _record_payment(doc, tid, b, h, amount="100.00")
    _issue_note(doc, tid, iid, h, amount="20.00")
    assert (
        doc.post(
            f"/api/v1/tenants/{tid}/payments/{pid}/refunds",
            json={"amount": "10.00", "reason": "audit probe"},
            headers=h,
        ).status_code
        == 200
    )
    rows = owner_db.execute(
        text(
            "SELECT action, resource_type, resource_id, reason, before_ref FROM audit_events "
            "WHERE tenant_id = :t AND resource_type IN ('refund', 'credit_note')"
        ),
        {"t": str(tid)},
    ).fetchall()
    actions = {r[0] for r in rows}
    assert {"refund.created", "credit_note.created", "credit_note.issued"} <= actions
    blob = " ".join(str(c) for r in rows for c in r if c is not None)
    assert "10.00" not in blob and "20.00" not in blob
    assert "audit probe" not in blob and "billing error" not in blob
    assert all(r[3] is None and r[4] is None for r in rows)


def test_concurrent_refund_single_winner(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="ref-race")
    doc = login_client(client, email=b["admin"].email)
    tid = str(b["tenant"].id)
    h = tenant_headers(tid)
    iid = _issue_invoice(doc, b["tenant"].id, b, h, rate="100.00")
    pid = _record_payment(doc, b["tenant"].id, b, h, amount="100.00")
    _allocate(doc, b["tenant"].id, pid, iid, "100.00", h)
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
            f"/api/v1/tenants/{tid}/payments/{pid}/refunds",
            json={"amount": "100.00", "reason": "race refund"},
            headers=h,
        )
        results.append(r.status_code)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for t in threads:
        t.start()
    gate.wait(timeout=30)
    for t in threads:
        t.join(timeout=120)
    assert sorted(results) == [200, 422], results
    payment = doc.get(f"/api/v1/tenants/{tid}/payments/{pid}", headers=h).json()
    assert payment["status"] == "refunded"
    assert payment["unallocated_amount"] == "0.00"


def test_concurrent_credit_note_single_winner(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="cn-race")
    doc = login_client(client, email=b["admin"].email)
    tid = str(b["tenant"].id)
    h = tenant_headers(tid)
    iid = _issue_invoice(doc, b["tenant"].id, b, h, rate="100.00")
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
            f"/api/v1/tenants/{tid}/invoices/{iid}/credit-notes",
            json={"amount": "100.00", "reason": "race credit"},
            headers=h,
        )
        if r.status_code != 200:
            results.append(r.status_code)
            return
        issue = c.post(
            f"/api/v1/tenants/{tid}/credit-notes/{r.json()['id']}/issue",
            json={},
            headers=h,
        )
        results.append(issue.status_code)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for t in threads:
        t.start()
    gate.wait(timeout=30)
    for t in threads:
        t.join(timeout=120)
    assert sorted(results) == [200, 422], results
    invoice = doc.get(f"/api/v1/tenants/{tid}/invoices/{iid}", headers=h).json()
    assert invoice["outstanding_amount"] == "0.00"


def test_concurrent_refund_vs_allocation_stays_valid(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    """Refund and allocation racing on the same payment must leave
    allocated + refunded ≤ captured, whatever the winner."""
    from decimal import Decimal

    b = provision_clinical(
        owner_db, make_owner_user, make_tenant, slug="ref-alloc-race"
    )
    doc = login_client(client, email=b["admin"].email)
    tid = str(b["tenant"].id)
    h = tenant_headers(tid)
    iid = _issue_invoice(doc, b["tenant"].id, b, h, rate="100.00")
    pid = _record_payment(doc, b["tenant"].id, b, h, amount="100.00")
    gate = threading.Barrier(3)
    results: list[int] = []

    def attempt(kind: str) -> None:
        c = TestClient(client.app, base_url="http://test")
        resp = c.post(
            "/api/v1/auth/login",
            json={"email": b["admin"].email, "password": "password-12345-abc"},
        )
        assert resp.status_code == 200
        gate.wait(timeout=30)
        if kind == "allocate":
            r = c.post(
                f"/api/v1/tenants/{tid}/payments/{pid}/allocations",
                json={"allocations": [{"invoice_id": iid, "amount": "100.00"}]},
                headers=h,
            )
        else:
            r = c.post(
                f"/api/v1/tenants/{tid}/payments/{pid}/refunds",
                json={"amount": "100.00", "reason": "race refund"},
                headers=h,
            )
        results.append(r.status_code)

    threads = [
        threading.Thread(target=attempt, args=("allocate",)),
        threading.Thread(target=attempt, args=("refund",)),
    ]
    for t in threads:
        t.start()
    gate.wait(timeout=30)
    for t in threads:
        t.join(timeout=120)
    assert all(code in (200, 409, 422) for code in results), results
    payment = doc.get(f"/api/v1/tenants/{tid}/payments/{pid}", headers=h).json()
    assert Decimal(payment["allocated_amount"]) + Decimal("0") <= Decimal("100.00")
    owned = doc.get(f"/api/v1/tenants/{tid}/payments/{pid}/refunds", headers=h).json()
    refunded = sum(Decimal(r["amount"]) for r in owned["items"])
    assert Decimal(payment["allocated_amount"]) + refunded <= Decimal("100.00")


def test_concurrent_credit_vs_allocation_stays_valid(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    """Credit issuance and allocation racing on the same invoice must leave
    allocated + credited ≤ invoice total, whatever the winner."""
    from decimal import Decimal

    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="cn-alloc-race")
    doc = login_client(client, email=b["admin"].email)
    tid = str(b["tenant"].id)
    h = tenant_headers(tid)
    iid = _issue_invoice(doc, b["tenant"].id, b, h, rate="100.00")
    pid = _record_payment(doc, b["tenant"].id, b, h, amount="100.00")
    gate = threading.Barrier(3)
    results: list[int] = []

    def attempt(kind: str) -> None:
        c = TestClient(client.app, base_url="http://test")
        resp = c.post(
            "/api/v1/auth/login",
            json={"email": b["admin"].email, "password": "password-12345-abc"},
        )
        assert resp.status_code == 200
        gate.wait(timeout=30)
        if kind == "allocate":
            r = c.post(
                f"/api/v1/tenants/{tid}/payments/{pid}/allocations",
                json={"allocations": [{"invoice_id": iid, "amount": "60.00"}]},
                headers=h,
            )
            results.append(r.status_code)
        else:
            created = c.post(
                f"/api/v1/tenants/{tid}/invoices/{iid}/credit-notes",
                json={"amount": "100.00", "reason": "race credit"},
                headers=h,
            )
            if created.status_code != 200:
                results.append(created.status_code)
                return
            issue = c.post(
                f"/api/v1/tenants/{tid}/credit-notes/{created.json()['id']}/issue",
                json={},
                headers=h,
            )
            results.append(issue.status_code)

    threads = [
        threading.Thread(target=attempt, args=("allocate",)),
        threading.Thread(target=attempt, args=("credit",)),
    ]
    for t in threads:
        t.start()
    gate.wait(timeout=30)
    for t in threads:
        t.join(timeout=120)
    assert all(code in (200, 409, 422) for code in results), results
    invoice = doc.get(f"/api/v1/tenants/{tid}/invoices/{iid}", headers=h).json()
    notes = doc.get(
        f"/api/v1/tenants/{tid}/invoices/{iid}/credit-notes", headers=h
    ).json()
    credited = sum(
        Decimal(n["amount"]) for n in notes["items"] if n["status"] == "issued"
    )
    assert Decimal(invoice["allocated_amount"]) + credited <= Decimal("100.00")
    assert Decimal(invoice["outstanding_amount"]) >= Decimal("0.00")
    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="cn-race")
    doc = login_client(client, email=b["admin"].email)
    tid = str(b["tenant"].id)
    h = tenant_headers(tid)
    iid = _issue_invoice(doc, b["tenant"].id, b, h, rate="100.00")
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
            f"/api/v1/tenants/{tid}/invoices/{iid}/credit-notes",
            json={"amount": "100.00", "reason": "race credit"},
            headers=h,
        )
        if r.status_code != 200:
            results.append(r.status_code)
            return
        issue = c.post(
            f"/api/v1/tenants/{tid}/credit-notes/{r.json()['id']}/issue",
            json={},
            headers=h,
        )
        results.append(issue.status_code)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for t in threads:
        t.start()
    gate.wait(timeout=30)
    for t in threads:
        t.join(timeout=120)
    assert sorted(results) == [200, 422], results
    invoice = doc.get(f"/api/v1/tenants/{tid}/invoices/{iid}", headers=h).json()
    assert invoice["outstanding_amount"] == "0.00"
