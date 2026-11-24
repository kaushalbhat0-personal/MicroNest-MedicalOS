"""P1.3 clinic operations dashboard: composition, isolation, metric integrity."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from tests.helpers import login_client, provision_scheduling, tenant_headers

UTC = timezone.utc


def _setup(owner_db, make_owner_user, make_tenant):
    return provision_scheduling(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=f"ops-{uuid.uuid4().hex[:6]}",
        admin_email=f"ops-{uuid.uuid4().hex[:6]}@example.com",
        patient_phone="+919811122233",
    )


def _auth(client, b):
    return login_client(client, email=b["admin"].email), tenant_headers(str(b["tenant"].id))


def _dash(doc, tid, lid, h, **params):
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"/api/v1/tenants/{tid}/locations/{lid}/operations-dashboard"
    if qs:
        url = f"{url}?{qs}"
    return doc.get(url, headers=h)


def test_dashboard_appointment_and_queue_counts(
    client, owner_db, make_owner_user, make_tenant
):
    b = _setup(owner_db, make_owner_user, make_tenant)
    doc, h = _auth(client, b)
    tid, lid = b["tenant"].id, b["location"].id

    future = (datetime.now(UTC) + timedelta(hours=2)).replace(second=0, microsecond=0)
    # Waiting (scheduled)
    r1 = doc.post(
        f"/api/v1/tenants/{tid}/appointments",
        headers={**h, "Idempotency-Key": "ops-a1"},
        json={
            "patient_id": str(b["patient"].id),
            "practitioner_id": str(b["practitioner"].id),
            "location_id": str(lid),
            "start": future.isoformat(),
            "duration_minutes": 15,
        },
    )
    assert r1.status_code == 200, r1.text
    # Checked in (walk-in allows now)
    r2 = doc.post(
        f"/api/v1/tenants/{tid}/appointments",
        headers={**h, "Idempotency-Key": "ops-a2"},
        json={
            "patient_id": str(b["patient"].id),
            "practitioner_id": str(b["practitioner"].id),
            "location_id": str(lid),
            "start": datetime.now(UTC).isoformat(),
            "duration_minutes": 15,
            "walk_in": True,
        },
    )
    assert r2.status_code == 200, r2.text

    dash = _dash(doc, tid, lid, h)
    assert dash.status_code == 200, dash.text
    body = dash.json()
    assert body["location_id"] == str(lid)
    assert body["timezone"]
    assert body["appointments"]["scheduled_today"] >= 2
    assert body["appointments"]["waiting"] >= 1
    assert body["appointments"]["checked_in"] >= 1
    assert body["reception"]["checked_in"] == body["appointments"]["checked_in"]
    assert any(a["id"] == r2.json()["id"] for a in body["todays_appointments"])
    assert any(a["queue_token"] is not None for a in body["todays_appointments"])

    # Reconcile with reception-queue
    board = doc.get(
        f"/api/v1/tenants/{tid}/locations/{lid}/reception-queue", headers=h
    )
    assert board.status_code == 200
    assert len(board.json()["checked_in"]) == body["reception"]["checked_in"]
    assert len(board.json()["waiting"]) == body["reception"]["waiting"]


def test_followup_and_billing_metrics(client, owner_db, make_owner_user, make_tenant):
    b = _setup(owner_db, make_owner_user, make_tenant)
    doc, h = _auth(client, b)
    tid, lid, pid = b["tenant"].id, b["location"].id, b["patient"].id

    due = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
    overdue = due - timedelta(days=2)
    fu = doc.post(
        f"/api/v1/tenants/{tid}/follow-ups",
        headers=h,
        json={
            "patient_id": str(pid),
            "location_id": str(lid),
            "due_at": due.isoformat().replace("+00:00", "Z"),
            "category": "manual",
            "reason": "Ops follow-up due",
            "source_type": "manual",
        },
    )
    assert fu.status_code == 200, fu.text
    fu2 = doc.post(
        f"/api/v1/tenants/{tid}/follow-ups",
        headers=h,
        json={
            "patient_id": str(pid),
            "location_id": str(lid),
            "due_at": overdue.isoformat().replace("+00:00", "Z"),
            "category": "manual",
            "reason": "Ops follow-up overdue",
            "source_type": "manual",
        },
    )
    assert fu2.status_code == 200, fu2.text

    inv = doc.post(
        f"/api/v1/tenants/{tid}/invoices",
        headers=h,
        json={
            "patient_id": str(pid),
            "location_id": str(lid),
            "items": [{"description": "Consult", "quantity": "1", "unit_rate": "500.00"}],
        },
    )
    assert inv.status_code == 200, inv.text
    issued = doc.post(
        f"/api/v1/tenants/{tid}/invoices/{inv.json()['id']}/issue",
        headers=h,
        json={},
    )
    assert issued.status_code == 200, issued.text

    pay = doc.post(
        f"/api/v1/tenants/{tid}/payments",
        headers=h,
        json={
            "patient_id": str(pid),
            "location_id": str(lid),
            "amount": "100.00",
            "method": "cash",
        },
    )
    assert pay.status_code == 200, pay.text

    dash = _dash(doc, tid, lid, h)
    assert dash.status_code == 200, dash.text
    body = dash.json()
    assert body["follow_ups"]["due_today"] >= 1
    assert body["follow_ups"]["overdue"] >= 1
    assert body["billing"]["outstanding_invoice_count"] >= 1
    assert float(body["billing"]["outstanding_amount"]) >= 500.0
    assert body["billing"]["payments_today_count"] >= 1
    assert float(body["billing"]["payments_today_amount"]) >= 100.0


def test_tenant_and_location_isolation(
    client, owner_db, make_owner_user, make_tenant
):
    a = _setup(owner_db, make_owner_user, make_tenant)
    b = _setup(owner_db, make_owner_user, make_tenant)
    doc_a, ha = _auth(client, a)
    # Wrong tenant id with A's session
    r = _dash(doc_a, b["tenant"].id, b["location"].id, ha)
    assert r.status_code == 404
    # Wrong location under A's tenant
    r2 = _dash(doc_a, a["tenant"].id, b["location"].id, ha)
    assert r2.status_code in (403, 404)


def test_restricted_role_omits_billing_section(
    client, owner_db, make_owner_user, make_tenant
):
    from app.modules.identity import service as identity_service
    from app.modules.tenancy import service as tenancy_service

    b = _setup(owner_db, make_owner_user, make_tenant)
    nurse = identity_service.create_user(
        owner_db,
        email=f"ops-nurse-{uuid.uuid4().hex[:6]}@example.com",
        display_name="Ops Nurse",
        password="password-12345-abc",
    )
    tenancy_service.create_membership(
        owner_db,
        user=nurse,
        tenant=b["tenant"],
        role=tenancy_service.get_seed_role(owner_db, "nurse"),
    )
    owner_db.commit()

    nurse_client = login_client(client, email=nurse.email)
    h = tenant_headers(str(b["tenant"].id))
    dash = _dash(nurse_client, b["tenant"].id, b["location"].id, h)
    assert dash.status_code == 200, dash.text
    body = dash.json()
    assert body["appointments"] is not None
    assert body["billing"] is None
    assert "billing" in body["sections_omitted"]


def test_empty_clinic_and_invalid_day(
    client, owner_db, make_owner_user, make_tenant
):
    b = _setup(owner_db, make_owner_user, make_tenant)
    doc, h = _auth(client, b)
    tid, lid = b["tenant"].id, b["location"].id
    dash = _dash(doc, tid, lid, h)
    assert dash.status_code == 200
    body = dash.json()
    assert body["appointments"]["scheduled_today"] == 0
    assert body["todays_appointments"] == []
    assert body["availability"] is not None

    bad = _dash(doc, tid, lid, h, day="not-a-date")
    assert bad.status_code == 422
    far = _dash(doc, tid, lid, h, day="1990-01-01")
    assert far.status_code == 422


def test_get_is_read_only(client, owner_db, make_owner_user, make_tenant):
    b = _setup(owner_db, make_owner_user, make_tenant)
    doc, h = _auth(client, b)
    tid, lid = b["tenant"].id, b["location"].id
    before = _dash(doc, tid, lid, h).json()
    after = _dash(doc, tid, lid, h).json()
    assert before["appointments"] == after["appointments"]
    assert before["service_date"] == after["service_date"]


def test_followup_location_day_midnight_boundary(
    client, owner_db, make_owner_user, make_tenant
):
    """Ops KPIs use location TZ day; workspace UTC buckets stay independent."""
    from zoneinfo import ZoneInfo

    from app.modules.communications import service as comms

    b = _setup(owner_db, make_owner_user, make_tenant)
    # Default location TZ is Asia/Kolkata
    tz = ZoneInfo("Asia/Kolkata")
    service_day = datetime.now(tz).date()
    start_local = datetime.combine(service_day, datetime.min.time()).replace(tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(UTC)
    end_utc = end_local.astimezone(UTC)

    # Just inside today (local midnight + 1 minute)
    due_today = start_utc + timedelta(minutes=1)
    # Just before today → overdue
    overdue_at = start_utc - timedelta(minutes=1)
    # At end boundary → upcoming
    upcoming_at = end_utc

    for when, reason in (
        (due_today, "loc-day due"),
        (overdue_at, "loc-day overdue"),
        (upcoming_at, "loc-day upcoming"),
    ):
        comms.create_follow_up(
            owner_db,
            tenant_id=b["tenant"].id,
            actor_id=b["admin"].id,
            patient_id=b["patient"].id,
            location_id=b["location"].id,
            due_at=when,
            category="manual",
            reason=reason,
        )
    owner_db.commit()

    counts = comms.count_follow_ups_for_interval(
        owner_db,
        tenant_id=b["tenant"].id,
        location_id=b["location"].id,
        start_utc=start_utc,
        end_utc=end_utc,
    )
    assert counts["due_today"] == 1
    assert counts["overdue"] == 1
    assert counts["upcoming"] == 1

    doc, h = _auth(client, b)
    dash = _dash(doc, b["tenant"].id, b["location"].id, h, day=str(service_day))
    assert dash.status_code == 200, dash.text
    body = dash.json()
    assert body["follow_ups"]["due_today"] == 1
    assert body["follow_ups"]["overdue"] == 1
    assert body["follow_ups"]["upcoming"] == 1


def test_billing_aggregation_complete_over_500(
    owner_db, make_owner_user, make_tenant
):
    """Outstanding totals must include all open invoices, not a 500-row sample."""
    from decimal import Decimal

    from sqlalchemy import select

    from app.modules.billing import invoices as inv_svc
    from app.modules.billing import models as billing_m

    b = _setup(owner_db, make_owner_user, make_tenant)
    tid, lid, pid = b["tenant"].id, b["location"].id, b["patient"].id
    actor = b["admin"].id
    n = 505
    for i in range(n):
        inv = inv_svc.create_invoice(
            owner_db,
            tenant_id=tid,
            actor_id=actor,
            patient_id=pid,
            location_id=lid,
            items=[{"description": f"Line {i}", "quantity": "1", "unit_rate": "10.00"}],
        )
        inv_svc.issue_invoice(
            owner_db, tenant_id=tid, invoice_id=inv.id, actor_id=actor
        )
    # One draft must not count
    inv_svc.create_invoice(
        owner_db,
        tenant_id=tid,
        actor_id=actor,
        patient_id=pid,
        location_id=lid,
        items=[{"description": "Draft", "quantity": "1", "unit_rate": "999.00"}],
    )
    owner_db.commit()

    count, amount = inv_svc.location_outstanding_summary(
        owner_db, tenant_id=tid, location_id=lid
    )
    assert count == n
    assert amount == Decimal("10.00") * n

    sample = list(
        owner_db.execute(
            select(billing_m.Invoice)
            .where(
                billing_m.Invoice.tenant_id == tid,
                billing_m.Invoice.location_id == lid,
                billing_m.Invoice.status == billing_m.INVOICE_ISSUED,
            )
            .limit(3)
        ).scalars()
    )
    for inv in sample:
        assert inv_svc.outstanding_for_invoice(owner_db, invoice=inv) == Decimal("10.00")


def test_workspace_context_permissions(client, owner_db, make_owner_user, make_tenant):
    b = _setup(owner_db, make_owner_user, make_tenant)
    doc, h = _auth(client, b)
    tid = b["tenant"].id
    r = doc.get(f"/api/v1/tenants/{tid}/workspace-context", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tenant_id"] == str(tid)
    assert "appointment.read" in body["permissions"]
    assert "billing.read" in body["permissions"]
    assert body["role"] == "tenant_admin"


def test_appointment_detail_list_signals_truncation(
    client, owner_db, make_owner_user, make_tenant, monkeypatch
):
    """Metrics stay complete; detail list reports truncated when over limit."""
    from app.modules.operations import service as ops_svc
    from app.modules.scheduling import service as sched_svc

    monkeypatch.setattr(ops_svc, "APPOINTMENT_DETAIL_LIMIT", 5)

    b = _setup(owner_db, make_owner_user, make_tenant)
    tid, lid = b["tenant"].id, b["location"].id
    base = (datetime.now(UTC) + timedelta(hours=1)).replace(second=0, microsecond=0)
    for i in range(8):
        sched_svc.create_appointment(
            owner_db,
            tenant_id=tid,
            actor_id=b["admin"].id,
            patient_id=b["patient"].id,
            practitioner_id=b["practitioner"].id,
            location_id=lid,
            start=base + timedelta(minutes=15 * i),
            duration_minutes=15,
            idempotency_key=f"ops-trunc-{i}-{uuid.uuid4().hex[:8]}",
        )
    owner_db.commit()

    doc, h = _auth(client, b)
    dash = _dash(doc, tid, lid, h)
    assert dash.status_code == 200, dash.text
    body = dash.json()
    assert body["appointments"]["scheduled_today"] >= 8
    meta = body["appointments_list"]
    assert meta["limit"] == 5
    assert meta["returned"] == 5
    assert meta["total"] >= 8
    assert meta["truncated"] is True
    assert len(body["todays_appointments"]) == 5
    assert body["follow_up_day_basis"] in (None, "location_service_day")


def test_followup_excludes_completed_cancelled_snoozed_from_due(
    owner_db, make_owner_user, make_tenant
):
    from zoneinfo import ZoneInfo

    from app.modules.communications import models as fu_m
    from app.modules.communications import service as comms

    b = _setup(owner_db, make_owner_user, make_tenant)
    tz = ZoneInfo("Asia/Kolkata")
    service_day = datetime.now(tz).date()
    start_local = datetime.combine(service_day, datetime.min.time()).replace(tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(UTC)
    end_utc = end_local.astimezone(UTC)
    due = start_utc + timedelta(hours=3)

    open_fu = comms.create_follow_up(
        owner_db,
        tenant_id=b["tenant"].id,
        actor_id=b["admin"].id,
        patient_id=b["patient"].id,
        location_id=b["location"].id,
        due_at=due,
        category="manual",
        reason="open due",
        source_type="manual",
        source_id=uuid.uuid4(),
    )
    done = comms.create_follow_up(
        owner_db,
        tenant_id=b["tenant"].id,
        actor_id=b["admin"].id,
        patient_id=b["patient"].id,
        location_id=b["location"].id,
        due_at=due + timedelta(minutes=1),
        category="manual",
        reason="done",
        source_type="manual",
        source_id=uuid.uuid4(),
    )
    comms.transition_follow_up(
        owner_db,
        tenant_id=b["tenant"].id,
        follow_up_id=done.id,
        actor_id=b["admin"].id,
        new_status=fu_m.FU_COMPLETED,
        outcome="completed in test",
    )
    snoozed = comms.create_follow_up(
        owner_db,
        tenant_id=b["tenant"].id,
        actor_id=b["admin"].id,
        patient_id=b["patient"].id,
        location_id=b["location"].id,
        due_at=due + timedelta(minutes=2),
        category="manual",
        reason="snooze me",
        source_type="manual",
        source_id=uuid.uuid4(),
    )
    comms.transition_follow_up(
        owner_db,
        tenant_id=b["tenant"].id,
        follow_up_id=snoozed.id,
        actor_id=b["admin"].id,
        new_status=fu_m.FU_SNOOZED,
        snooze_until=end_utc + timedelta(days=1),
    )
    owner_db.commit()

    counts = comms.count_follow_ups_for_interval(
        owner_db,
        tenant_id=b["tenant"].id,
        location_id=b["location"].id,
        start_utc=start_utc,
        end_utc=end_utc,
    )
    assert counts["due_today"] >= 1
    # completed excluded; snoozed with due inside window excluded from due_today
    assert open_fu.id is not None
    assert counts["due_today"] == 1
