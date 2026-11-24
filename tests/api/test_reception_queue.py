"""P0.2 reception queue tokens + board (real Postgres concurrency)."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

from tests.helpers import login_client, provision_scheduling, tenant_headers


UTC = timezone.utc


def _future_start(hours: int = 2) -> str:
    return (
        (datetime.now(UTC) + timedelta(hours=hours))
        .replace(second=0, microsecond=0)
        .isoformat()
    )


def test_check_in_assigns_unique_queue_token(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_scheduling(owner_db, make_owner_user, make_tenant, slug="q-tok-a")
    doc = login_client(client, email=b["admin"].email)
    tid = b["tenant"].id
    h = tenant_headers(tid)
    lid = str(b["location"].id)
    created = []
    for i in range(2):
        r = doc.post(
            f"/api/v1/tenants/{tid}/appointments",
            json={
                "patient_id": str(b["patient"].id),
                "practitioner_id": str(b["practitioner"].id),
                "location_id": lid,
                "start": _future_start(hours=3 + i),
                "duration_minutes": 15,
            },
            headers={**h, "Idempotency-Key": f"q-tok-a-{i}"},
        )
        assert r.status_code == 200, r.text
        created.append(r.json())
        assert created[-1]["queue_token"] is None

    tokens = []
    for body in created:
        tr = doc.post(
            f"/api/v1/tenants/{tid}/appointments/{body['id']}/status",
            json={"status": "checked_in"},
            headers=h,
        )
        assert tr.status_code == 200, tr.text
        assert tr.json()["status"] == "checked_in"
        assert tr.json()["queue_token"] is not None
        assert tr.json()["queue_date"] is not None
        tokens.append(tr.json()["queue_token"])
    assert tokens == sorted(tokens)
    assert len(set(tokens)) == 2

    # Re-check-in is idempotent: same token.
    again = doc.post(
        f"/api/v1/tenants/{tid}/appointments/{created[0]['id']}/status",
        json={"status": "checked_in"},
        headers=h,
    )
    assert again.status_code == 200
    assert again.json()["queue_token"] == tokens[0]

    board = doc.get(
        f"/api/v1/tenants/{tid}/locations/{lid}/reception-queue",
        headers=h,
    )
    assert board.status_code == 200, board.text
    payload = board.json()
    assert payload["location_id"] == lid
    assert len(payload["checked_in"]) == 2
    assert {row["queue_token"] for row in payload["checked_in"]} == set(tokens)


def test_walk_in_gets_token_and_checked_in(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_scheduling(owner_db, make_owner_user, make_tenant, slug="q-walk")
    doc = login_client(client, email=b["admin"].email)
    tid = b["tenant"].id
    h = tenant_headers(tid)
    r = doc.post(
        f"/api/v1/tenants/{tid}/appointments",
        json={
            "patient_id": str(b["patient"].id),
            "practitioner_id": str(b["practitioner"].id),
            "location_id": str(b["location"].id),
            "start": datetime.now(UTC).isoformat(),
            "duration_minutes": 15,
            "walk_in": True,
        },
        headers={**h, "Idempotency-Key": "q-walk-1"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "checked_in"
    assert body["queue_token"] == 1
    assert body["queue_date"] is not None
    assert body["notes"] == "walk-in"


def test_concurrent_check_in_unique_tokens(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_scheduling(owner_db, make_owner_user, make_tenant, slug="q-race")
    doc = login_client(client, email=b["admin"].email)
    tid = b["tenant"].id
    h = tenant_headers(tid)
    lid = str(b["location"].id)
    # Second patient for a second slot (same practitioner, non-overlapping).
    from app.modules.patients import service as patients_service

    other = patients_service.register_patient(
        owner_db,
        tenant_id=b["tenant"].id,
        display_name="Queue Race Patient",
        phone=None,
    )
    owner_db.commit()
    ids = []
    for i, patient in enumerate((b["patient"], other)):
        r = doc.post(
            f"/api/v1/tenants/{tid}/appointments",
            json={
                "patient_id": str(patient.id),
                "practitioner_id": str(b["practitioner"].id),
                "location_id": lid,
                "start": _future_start(hours=4 + i),
                "duration_minutes": 20,
            },
            headers={**h, "Idempotency-Key": f"q-race-{i}"},
        )
        assert r.status_code == 200, r.text
        ids.append(r.json()["id"])

    gate = threading.Barrier(3)
    results: list[dict] = []
    errors: list[str] = []

    def attempt(aid: str) -> None:
        try:
            gate.wait(timeout=10)
            resp = doc.post(
                f"/api/v1/tenants/{tid}/appointments/{aid}/status",
                json={"status": "checked_in"},
                headers=h,
            )
            results.append({"status_code": resp.status_code, "body": resp.json()})
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

    threads = [threading.Thread(target=attempt, args=(aid,)) for aid in ids]
    for t in threads:
        t.start()
    gate.wait(timeout=10)
    for t in threads:
        t.join(timeout=30)

    assert not errors, errors
    assert len(results) == 2
    assert all(r["status_code"] == 200 for r in results)
    tokens = sorted(r["body"]["queue_token"] for r in results)
    assert tokens == [1, 2]


def test_reception_queue_location_isolation(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    a = provision_scheduling(owner_db, make_owner_user, make_tenant, slug="q-iso-a")
    b = provision_scheduling(owner_db, make_owner_user, make_tenant, slug="q-iso-b")
    doc_a = login_client(client, email=a["admin"].email)
    ha = tenant_headers(a["tenant"].id)
    # Book + check in on tenant A
    created = doc_a.post(
        f"/api/v1/tenants/{a['tenant'].id}/appointments",
        json={
            "patient_id": str(a["patient"].id),
            "practitioner_id": str(a["practitioner"].id),
            "location_id": str(a["location"].id),
            "start": _future_start(hours=5),
            "duration_minutes": 15,
            "walk_in": True,
        },
        headers={**ha, "Idempotency-Key": "q-iso-walk"},
    )
    assert created.status_code == 200, created.text

    # Tenant B cannot read A's location queue (404 / forbidden closed).
    doc_b = login_client(client, email=b["admin"].email)
    hb = tenant_headers(b["tenant"].id)
    leaked = doc_b.get(
        f"/api/v1/tenants/{b['tenant'].id}/locations/{a['location'].id}/reception-queue",
        headers=hb,
    )
    assert leaked.status_code in (403, 404), leaked.text

    # Cross-tenant id on A's path with B's session also fails closed.
    cross = doc_b.get(
        f"/api/v1/tenants/{a['tenant'].id}/locations/{a['location'].id}/reception-queue",
        headers=hb,
    )
    assert cross.status_code in (403, 404), cross.text
