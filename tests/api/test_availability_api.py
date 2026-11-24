"""Working hours + free-slot availability (staff)."""

from datetime import date, timedelta

from tests.helpers import login_client, provision_scheduling, tenant_headers


def test_working_hours_and_availability(client, owner_db, make_owner_user, make_tenant):
    base = provision_scheduling(
        owner_db,
        make_owner_user,
        make_tenant,
        slug="avail-a",
        admin_email="avail-a@example.com",
    )
    tid = str(base["tenant"].id)
    lid = str(base["location"].id)
    pid = str(base["practitioner"].id)
    admin = login_client(client, email=base["admin"].email)
    h = tenant_headers(tid)

    # Monday–Friday 09:00–12:00, 30-min slots
    put = admin.put(
        f"/api/v1/tenants/{tid}/locations/{lid}/working-hours",
        headers=h,
        json={
            "windows": [
                {
                    "weekday": d,
                    "start_local": "09:00:00",
                    "end_local": "12:00:00",
                    "slot_minutes": 30,
                }
                for d in range(5)
            ]
        },
    )
    assert put.status_code == 200, put.text
    assert len(put.json()["windows"]) == 5

    # Find next weekday Mon–Fri
    day = date.today() + timedelta(days=1)
    while day.weekday() > 4:
        day += timedelta(days=1)

    avail = admin.get(
        f"/api/v1/tenants/{tid}/availability"
        f"?practitioner_id={pid}&location_id={lid}&day={day.isoformat()}",
        headers=h,
    )
    assert avail.status_code == 200, avail.text
    body = avail.json()
    assert body["slot_minutes"] == 30
    assert isinstance(body["slots"], list)
    # Slots never include patient identifiers
    for slot in body["slots"]:
        assert set(slot.keys()) == {"start_at", "end_at"}
