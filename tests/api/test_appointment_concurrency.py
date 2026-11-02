"""Double-booking under concurrency: two simultaneous requests for the same
practitioner slot must serialize — exactly one wins (200), the other gets
409. Proves the advisory-lock + overlap check holds under race conditions."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.platform.time import UTC
from tests.helpers import login_client, provision_scheduling, tenant_headers


def test_concurrent_same_slot_single_winner(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from app.modules.patients import service as patients_service

    b = provision_scheduling(owner_db, make_owner_user, make_tenant, slug="sched-race")
    other = patients_service.register_patient(
        owner_db, tenant_id=b["tenant"].id, display_name="Second Patient"
    )
    owner_db.commit()
    tid = str(b["tenant"].id)
    start = (
        (datetime.now(UTC) + timedelta(days=2))
        .replace(hour=10, minute=0, second=0, microsecond=0)
        .isoformat()
    )
    gate = threading.Barrier(3)
    results: list[int] = []

    def attempt(patient_id: str) -> None:
        c = TestClient(client.app, base_url="http://test")
        resp = c.post(
            "/api/v1/auth/login",
            json={"email": b["admin"].email, "password": "password-12345-abc"},
        )
        assert resp.status_code == 200
        gate.wait(timeout=30)
        r = c.post(
            f"/api/v1/tenants/{tid}/appointments",
            json={
                "patient_id": patient_id,
                "practitioner_id": str(b["practitioner"].id),
                "location_id": str(b["location"].id),
                "start": start,
                "duration_minutes": 30,
            },
            headers=tenant_headers(tid),
        )
        results.append(r.status_code)

    threads = [
        threading.Thread(target=attempt, args=(str(b["patient"].id),)),
        threading.Thread(target=attempt, args=(str(other.id),)),
    ]
    for t in threads:
        t.start()
    gate.wait(timeout=30)
    for t in threads:
        t.join(timeout=120)
    assert sorted(results) == [200, 409], results
    # Exactly one row persisted.
    listed = (
        login_client(client, email=b["admin"].email)
        .get(f"/api/v1/tenants/{tid}/appointments", headers=tenant_headers(tid))
        .json()
    )
    assert len(listed["items"]) == 1
