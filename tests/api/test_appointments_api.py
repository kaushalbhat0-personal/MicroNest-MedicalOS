"""Scheduling + patient API: contracts, validation, pagination, idempotency,
audit and outbox side-effects over HTTP (app role, RLS enforced)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from app.platform.time import UTC
from tests.helpers import login_client, provision_scheduling, tenant_headers


def _future_iso(*, days: int = 2, hour: int = 10) -> str:
    base = datetime.now(UTC) + timedelta(days=days)
    return base.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


def _payload(bundle, **kw):  # type: ignore[no-untyped-def]
    body = {
        "patient_id": str(bundle["patient"].id),
        "practitioner_id": str(bundle["practitioner"].id),
        "location_id": str(bundle["location"].id),
        "start": _future_iso(),
        "duration_minutes": 30,
    }
    body.update(kw)
    return body


def _setup(client, owner_db, make_owner_user, make_tenant, **kw):  # type: ignore[no-untyped-def]
    bundle = provision_scheduling(owner_db, make_owner_user, make_tenant, **kw)
    c = login_client(client, email=bundle["admin"].email)
    headers = tenant_headers(bundle["tenant"].id)
    return bundle, c, headers


def test_create_and_get_roundtrip(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b, c, h = _setup(client, owner_db, make_owner_user, make_tenant)
    r = c.post(
        f"/api/v1/tenants/{b['tenant'].id}/appointments", json=_payload(b), headers=h
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "scheduled"
    assert body["tenant_id"] == str(b["tenant"].id)
    start = datetime.fromisoformat(body["start_at"].replace("Z", "+00:00"))
    assert start.tzinfo is not None
    got = c.get(
        f"/api/v1/tenants/{b['tenant'].id}/appointments/{body['id']}", headers=h
    )
    assert got.status_code == 200
    assert got.json()["id"] == body["id"]


def test_create_past_start_is_422_envelope(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b, c, h = _setup(client, owner_db, make_owner_user, make_tenant)
    past = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    r = c.post(
        f"/api/v1/tenants/{b['tenant'].id}/appointments",
        json=_payload(b, start=past),
        headers=h,
    )
    assert r.status_code == 422, r.text
    for key in ("type", "title", "status", "detail", "trace_id"):
        assert key in r.json(), key


def test_create_overlap_is_409(client, owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b, c, h = _setup(client, owner_db, make_owner_user, make_tenant)
    start = _future_iso()
    assert (
        c.post(
            f"/api/v1/tenants/{b['tenant'].id}/appointments",
            json=_payload(b, start=start),
            headers=h,
        ).status_code
        == 200
    )
    r = c.post(
        f"/api/v1/tenants/{b['tenant'].id}/appointments",
        json=_payload(b, start=start),
        headers=h,
    )
    assert r.status_code == 409, r.text
    assert r.json()["type"].endswith("/conflict")


def test_idempotency_key_header_replays_same_row(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b, c, h = _setup(client, owner_db, make_owner_user, make_tenant)
    url = f"/api/v1/tenants/{b['tenant'].id}/appointments"
    headers = {**h, "Idempotency-Key": f"idem-{uuid.uuid4().hex}"}
    first = c.post(url, json=_payload(b), headers=headers)
    assert first.status_code == 200, first.text
    second = c.post(url, json=_payload(b), headers=headers)
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    listed = c.get(url, headers=h).json()
    assert listed["next_cursor"] is None
    assert len(listed["items"]) == 1


def test_list_pagination_and_filters(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b, c, h = _setup(client, owner_db, make_owner_user, make_tenant)
    url = f"/api/v1/tenants/{b['tenant'].id}/appointments"
    for day in (2, 3, 4):
        r = c.post(url, json=_payload(b, start=_future_iso(days=day)), headers=h)
        assert r.status_code == 200, r.text
    page1 = c.get(url, params={"limit": 2}, headers=h).json()
    assert len(page1["items"]) == 2
    assert page1["next_cursor"] is not None
    page2 = c.get(
        url, params={"limit": 2, "cursor": page1["next_cursor"]}, headers=h
    ).json()
    assert len(page2["items"]) == 1
    assert page2["next_cursor"] is None
    # Ordered by start ascending across pages.
    starts = [i["start_at"] for i in page1["items"]] + [
        i["start_at"] for i in page2["items"]
    ]
    assert starts == sorted(starts)
    # Status filter.
    only = c.get(url, params={"status": "scheduled"}, headers=h).json()
    assert len(only["items"]) == 3
    # Unknown status is 422, not 500.
    bad = c.get(url, params={"status": "teleporting"}, headers=h)
    assert bad.status_code == 422


def test_lifecycle_over_http(client, owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b, c, h = _setup(client, owner_db, make_owner_user, make_tenant)
    tid = b["tenant"].id
    created = c.post(
        f"/api/v1/tenants/{tid}/appointments", json=_payload(b), headers=h
    ).json()
    aid = created["id"]
    for nxt in ("confirmed", "checked_in", "completed"):
        r = c.post(
            f"/api/v1/tenants/{tid}/appointments/{aid}/status",
            json={"status": nxt},
            headers=h,
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == nxt
    # Terminal: no exit.
    assert (
        c.post(
            f"/api/v1/tenants/{tid}/appointments/{aid}/status",
            json={"status": "scheduled"},
            headers=h,
        ).status_code
        == 422
    )


def test_cancel_records_reason(client, owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b, c, h = _setup(client, owner_db, make_owner_user, make_tenant)
    tid = b["tenant"].id
    created = c.post(
        f"/api/v1/tenants/{tid}/appointments", json=_payload(b), headers=h
    ).json()
    r = c.post(
        f"/api/v1/tenants/{tid}/appointments/{created['id']}/cancel",
        json={"reason": "patient request"},
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"
    assert r.json()["cancel_reason"] == "patient request"
    assert r.json()["cancelled_by"] is not None


def test_cancel_retry_is_idempotent(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b, c, h = _setup(client, owner_db, make_owner_user, make_tenant)
    tid = b["tenant"].id
    created = c.post(
        f"/api/v1/tenants/{tid}/appointments", json=_payload(b), headers=h
    ).json()
    url = f"/api/v1/tenants/{tid}/appointments/{created['id']}/cancel"
    assert c.post(url, json={}, headers=h).status_code == 200
    again = c.post(url, json={}, headers=h)
    assert again.status_code == 200
    assert again.json()["status"] == "cancelled"


def test_create_emits_audit_and_confirmation_outbox(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import text

    b, c, h = _setup(client, owner_db, make_owner_user, make_tenant)
    tid = b["tenant"].id
    r = c.post(f"/api/v1/tenants/{tid}/appointments", json=_payload(b), headers=h)
    assert r.status_code == 200, r.text
    aid = r.json()["id"]
    audit_row = owner_db.execute(
        text(
            "SELECT action, resource_type, resource_id FROM audit_events "
            "WHERE tenant_id = :t AND resource_id = :r"
        ),
        {"t": str(tid), "r": aid},
    ).fetchone()
    assert audit_row is not None and audit_row[0] == "appointment.create"
    outbox_row = owner_db.execute(
        text("SELECT type, payload FROM outbox_events WHERE tenant_id = :t"),
        {"t": str(tid)},
    ).fetchall()
    kinds = {row[0] for row in outbox_row}
    assert "notification.requested" in kinds
    for row in outbox_row:
        if row[0] == "notification.requested":
            assert "appointment" in str(row[1]).lower() or "appointment_id" in str(
                row[1]
            )


def test_doctor_cannot_create_but_can_read(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from app.modules.tenancy import service as tenancy_service

    b, c, h = _setup(client, owner_db, make_owner_user, make_tenant)
    tid = b["tenant"].id
    created = c.post(f"/api/v1/tenants/{tid}/appointments", json=_payload(b), headers=h)
    assert created.status_code == 200
    doctor = make_owner_user(email="doc-sched@example.com")
    tenancy_service.create_membership(
        owner_db,
        user=doctor,
        tenant=b["tenant"],
        role=tenancy_service.get_seed_role(owner_db, "doctor"),
    )
    owner_db.commit()
    dc = login_client(client, email="doc-sched@example.com")
    dh = tenant_headers(tid)
    assert (
        dc.post(
            f"/api/v1/tenants/{tid}/appointments", json=_payload(b), headers=dh
        ).status_code
        == 403
    )
    assert dc.get(f"/api/v1/tenants/{tid}/appointments", headers=dh).status_code == 200


def test_unauthenticated_is_401(client, owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    from fastapi.testclient import TestClient

    b = provision_scheduling(owner_db, make_owner_user, make_tenant)
    anon = TestClient(client.app, base_url="http://test")
    assert anon.get(f"/api/v1/tenants/{b['tenant'].id}/appointments").status_code == 401


def test_patient_endpoints(client, owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b, c, h = _setup(client, owner_db, make_owner_user, make_tenant)
    tid = b["tenant"].id
    r = c.post(
        f"/api/v1/tenants/{tid}/patients",
        json={"display_name": "New Patient", "phone": "+919999999999"},
        headers=h,
    )
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    assert c.get(f"/api/v1/tenants/{tid}/patients/{pid}", headers=h).status_code == 200
    listed = c.get(f"/api/v1/tenants/{tid}/patients", headers=h).json()
    assert {p["id"] for p in listed} >= {pid, str(b["patient"].id)}
    # Blank name rejected.
    assert (
        c.post(
            f"/api/v1/tenants/{tid}/patients", json={"display_name": "x"}, headers=h
        ).status_code
        == 422
    )
