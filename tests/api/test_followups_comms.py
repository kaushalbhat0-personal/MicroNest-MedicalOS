"""P0.4 follow-ups, communication consent, logs, WhatsApp link."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from tests.helpers import login_client, provision_scheduling, tenant_headers


def _base(owner_db, make_owner_user, make_tenant):
    return provision_scheduling(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=f"fu-{uuid.uuid4().hex[:6]}",
        admin_email=f"fu-{uuid.uuid4().hex[:6]}@example.com",
        patient_phone="+919876543210",
    )


def test_followup_lifecycle_and_buckets(client, owner_db, make_owner_user, make_tenant):
    b = _base(owner_db, make_owner_user, make_tenant)
    tid, pid, lid = b["tenant"].id, b["patient"].id, b["location"].id
    doc = login_client(client, email=b["admin"].email)
    h = tenant_headers(str(tid))
    due = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat().replace("+00:00", "Z")

    created = doc.post(
        f"/api/v1/tenants/{tid}/follow-ups",
        headers=h,
        json={
            "patient_id": str(pid),
            "location_id": str(lid),
            "due_at": due,
            "category": "manual",
            "reason": "Call about labs",
            "source_type": "manual",
            "priority": "high",
            "assigned_user_id": str(b["admin"].id),
        },
    )
    assert created.status_code == 200, created.text
    fu_id = created.json()["id"]
    assert created.json()["status"] == "open"
    assert created.json()["due_at"].endswith("Z")

    mine = doc.get(
        f"/api/v1/tenants/{tid}/follow-ups?bucket=assigned_to_me", headers=h
    )
    assert mine.status_code == 200
    assert any(x["id"] == fu_id for x in mine.json())

    started = doc.post(
        f"/api/v1/tenants/{tid}/follow-ups/{fu_id}/transition",
        headers=h,
        json={"status": "in_progress"},
    )
    assert started.status_code == 200
    assert started.json()["status"] == "in_progress"

    snooze_until = (
        datetime.now(timezone.utc) + timedelta(days=1)
    ).isoformat().replace("+00:00", "Z")
    snoozed = doc.post(
        f"/api/v1/tenants/{tid}/follow-ups/{fu_id}/transition",
        headers=h,
        json={"status": "snoozed", "snooze_until": snooze_until},
    )
    assert snoozed.status_code == 200
    assert snoozed.json()["status"] == "snoozed"

    done = doc.post(
        f"/api/v1/tenants/{tid}/follow-ups/{fu_id}/transition",
        headers=h,
        json={"status": "completed", "outcome": "reached patient"},
    )
    assert done.status_code == 200
    assert done.json()["status"] == "completed"
    assert done.json()["completed_at"].endswith("Z")

    # Terminal: cannot reopen
    bad = doc.post(
        f"/api/v1/tenants/{tid}/follow-ups/{fu_id}/transition",
        headers=h,
        json={"status": "open"},
    )
    assert bad.status_code == 409


def test_followup_duplicate_active_source_blocked(
    client, owner_db, make_owner_user, make_tenant
):
    from app.modules.scheduling import service as sched

    b = _base(owner_db, make_owner_user, make_tenant)
    tid, pid, lid = b["tenant"].id, b["patient"].id, b["location"].id
    appt = sched.create_appointment(
        owner_db,
        tenant_id=tid,
        actor_id=b["admin"].id,
        patient_id=pid,
        practitioner_id=b["practitioner"].id,
        location_id=lid,
        start=datetime.now(timezone.utc) + timedelta(days=1),
        duration_minutes=30,
    )
    owner_db.commit()

    doc = login_client(client, email=b["admin"].email)
    h = tenant_headers(str(tid))
    due = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat().replace("+00:00", "Z")
    payload = {
        "patient_id": str(pid),
        "location_id": str(lid),
        "due_at": due,
        "category": "appointment",
        "reason": "Confirm attendance",
        "source_type": "appointment",
        "source_id": str(appt.id),
    }
    assert doc.post(f"/api/v1/tenants/{tid}/follow-ups", headers=h, json=payload).status_code == 200
    dup = doc.post(f"/api/v1/tenants/{tid}/follow-ups", headers=h, json=payload)
    assert dup.status_code == 409


def test_consent_fail_closed_revoke_and_history(
    client, owner_db, make_owner_user, make_tenant
):
    b = _base(owner_db, make_owner_user, make_tenant)
    tid, pid = b["tenant"].id, b["patient"].id
    doc = login_client(client, email=b["admin"].email)
    h = tenant_headers(str(tid))

    elig = doc.get(
        f"/api/v1/tenants/{tid}/patients/{pid}/communication-eligibility"
        f"?channel=whatsapp&purpose=care_followup",
        headers=h,
    )
    assert elig.status_code == 200
    assert elig.json()["status"] == "unknown"
    assert elig.json()["eligible"] is False

    # WhatsApp link requires consent by default
    denied = doc.post(
        f"/api/v1/tenants/{tid}/whatsapp-link",
        headers=h,
        json={"patient_id": str(pid), "purpose": "care_followup", "require_consent": True},
    )
    assert denied.status_code == 403

    granted = doc.post(
        f"/api/v1/tenants/{tid}/communication-consents",
        headers=h,
        json={
            "patient_id": str(pid),
            "channel": "whatsapp",
            "purpose": "care_followup",
            "status": "granted",
        },
    )
    assert granted.status_code == 200
    first_id = granted.json()["id"]

    link = doc.post(
        f"/api/v1/tenants/{tid}/whatsapp-link",
        headers=h,
        json={
            "patient_id": str(pid),
            "purpose": "care_followup",
            "message": "Hello from clinic",
            "require_consent": True,
        },
    )
    assert link.status_code == 200, link.text
    body = link.json()
    assert body["url"].startswith("https://wa.me/919876543210")
    assert "text=" in body["url"]
    assert body["auto_send"] is False
    assert body["delivery_tracked"] is False
    assert body["eligible"] is True

    # Purpose isolation: marketing still unknown
    mkt = doc.get(
        f"/api/v1/tenants/{tid}/patients/{pid}/communication-eligibility"
        f"?channel=whatsapp&purpose=marketing",
        headers=h,
    )
    assert mkt.json()["eligible"] is False

    revoked = doc.post(
        f"/api/v1/tenants/{tid}/communication-consents/revoke",
        headers=h,
        json={
            "patient_id": str(pid),
            "channel": "whatsapp",
            "purpose": "care_followup",
        },
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    assert revoked.json()["id"] != first_id

    after = doc.get(
        f"/api/v1/tenants/{tid}/patients/{pid}/communication-eligibility"
        f"?channel=whatsapp&purpose=care_followup",
        headers=h,
    )
    assert after.json()["status"] == "revoked"
    assert after.json()["eligible"] is False


def test_communication_log_and_isolation(
    client, owner_db, make_owner_user, make_tenant
):
    a = _base(owner_db, make_owner_user, make_tenant)
    b = provision_scheduling(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=f"fu2-{uuid.uuid4().hex[:6]}",
        admin_email=f"fu2-{uuid.uuid4().hex[:6]}@example.com",
    )
    ca = login_client(client, email=a["admin"].email)
    ha = tenant_headers(str(a["tenant"].id))

    logged = ca.post(
        f"/api/v1/tenants/{a['tenant'].id}/communication-logs",
        headers=ha,
        json={
            "patient_id": str(a["patient"].id),
            "channel": "phone",
            "purpose": "care_followup",
            "outcome": "no_answer",
            "note": "ring tone only",
        },
    )
    assert logged.status_code == 200, logged.text
    assert "message" not in logged.json()

    # Cross-tenant patient id → 404
    cross = ca.post(
        f"/api/v1/tenants/{a['tenant'].id}/communication-logs",
        headers=ha,
        json={
            "patient_id": str(b["patient"].id),
            "channel": "phone",
            "purpose": "care_followup",
            "outcome": "contacted",
        },
    )
    assert cross.status_code == 404

    listed = ca.get(
        f"/api/v1/tenants/{a['tenant'].id}/communication-logs"
        f"?patient_id={a['patient'].id}",
        headers=ha,
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    # Wrong tenant selector
    wrong = ca.get(
        f"/api/v1/tenants/{b['tenant'].id}/communication-logs",
        headers=ha,
    )
    assert wrong.status_code in (403, 404)


def test_patient_overview_includes_followup_counts(
    client, owner_db, make_owner_user, make_tenant
):
    b = _base(owner_db, make_owner_user, make_tenant)
    tid, pid, lid = b["tenant"].id, b["patient"].id, b["location"].id
    doc = login_client(client, email=b["admin"].email)
    h = tenant_headers(str(tid))
    due = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat().replace("+00:00", "Z")
    doc.post(
        f"/api/v1/tenants/{tid}/follow-ups",
        headers=h,
        json={
            "patient_id": str(pid),
            "location_id": str(lid),
            "due_at": due,
            "category": "manual",
            "reason": "Overdue call",
            "source_type": "manual",
        },
    )
    ov = doc.get(f"/api/v1/tenants/{tid}/patients/{pid}/overview", headers=h)
    assert ov.status_code == 200
    assert ov.json()["open_followups"] >= 1
    assert ov.json()["overdue_followups"] >= 1
