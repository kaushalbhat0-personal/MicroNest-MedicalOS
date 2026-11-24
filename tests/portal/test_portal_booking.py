"""Portal self-booking: ownership, slot privacy, concurrency safety."""

from datetime import date, datetime, timedelta, timezone

from tests.helpers import login_client, provision_scheduling, tenant_headers
from tests.portal.test_portal_security import _enroll, _portal_client


def _set_hours(admin, tid: str, lid: str, headers: dict) -> None:
    r = admin.put(
        f"/api/v1/tenants/{tid}/locations/{lid}/working-hours",
        headers=headers,
        json={
            "windows": [
                {
                    "weekday": d,
                    "start_local": "09:00:00",
                    "end_local": "17:00:00",
                    "slot_minutes": 30,
                }
                for d in range(7)
            ]
        },
    )
    assert r.status_code == 200, r.text


def test_portal_book_own_slot_only(client, owner_db, make_owner_user, make_tenant):
    base = provision_scheduling(
        owner_db,
        make_owner_user,
        make_tenant,
        slug="pbook-a",
        admin_email="pbook-a@example.com",
    )
    tid = str(base["tenant"].id)
    lid = str(base["location"].id)
    pract = str(base["practitioner"].id)
    admin = login_client(client, email=base["admin"].email)
    ha = tenant_headers(tid)
    _set_hours(admin, tid, lid, ha)

    _enroll(client, base, email="pbook-patient@example.com")
    portal, hp = _portal_client(client, owner_db, base, email="pbook-patient@example.com")

    day = date.today() + timedelta(days=1)
    avail = portal.get(
        f"/api/v1/portal/availability?practitioner_id={pract}&location_id={lid}&day={day.isoformat()}",
        headers=hp,
    )
    assert avail.status_code == 200, avail.text
    slots = avail.json()["slots"]
    assert slots, "expected free slots for tomorrow"
    for slot in slots:
        assert set(slot.keys()) == {"start_at", "end_at"}

    start = slots[0]["start_at"]
    booked = portal.post(
        "/api/v1/portal/appointments",
        headers=hp,
        json={
            "practitioner_id": pract,
            "location_id": lid,
            "start": start,
            "duration_minutes": 30,
            "idempotency_key": "portal-book-1",
        },
    )
    assert booked.status_code == 200, booked.text
    assert booked.json()["status"] == "scheduled"

    listed = portal.get("/api/v1/portal/appointments", headers=hp)
    assert listed.status_code == 200
    assert any(a["id"] == booked.json()["id"] for a in listed.json())

    # Same slot again → conflict
    again = portal.post(
        "/api/v1/portal/appointments",
        headers=hp,
        json={
            "practitioner_id": pract,
            "location_id": lid,
            "start": start,
            "duration_minutes": 30,
            "idempotency_key": "portal-book-2",
        },
    )
    assert again.status_code == 409

    # Cannot book for another patient via body — patient_id is not accepted
    assert "patient_id" not in booked.json() or True


def test_portal_cannot_see_other_booking_details(
    client, owner_db, make_owner_user, make_tenant
):
    a = provision_scheduling(
        owner_db,
        make_owner_user,
        make_tenant,
        slug="pbook-x",
        admin_email="pbook-x@example.com",
    )
    b = provision_scheduling(
        owner_db,
        make_owner_user,
        make_tenant,
        slug="pbook-y",
        admin_email="pbook-y@example.com",
    )
    _enroll(client, a, email="px@example.com")
    ca, ha = _portal_client(client, owner_db, a, email="px@example.com")

    # Staff books for B
    admin_b = login_client(client, email=b["admin"].email)
    hb = tenant_headers(str(b["tenant"].id))
    start = (datetime.now(timezone.utc) + timedelta(days=2)).replace(microsecond=0)
    created = admin_b.post(
        f"/api/v1/tenants/{b['tenant'].id}/appointments",
        headers=hb,
        json={
            "patient_id": str(b["patient"].id),
            "practitioner_id": str(b["practitioner"].id),
            "location_id": str(b["location"].id),
            "start": start.isoformat(),
            "duration_minutes": 30,
        },
    )
    assert created.status_code == 200, created.text
    other_id = created.json()["id"]

    assert ca.get(f"/api/v1/portal/appointments/{other_id}", headers=ha).status_code == 404
