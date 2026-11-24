"""P0.3 Patient 360° overview/timeline + portal release gates."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.modules.identity.models import User
from app.modules.portal.models import PortalLink
from tests.helpers import login_client, provision_clinical, provision_scheduling, tenant_headers
from tests.portal.test_portal_security import _enroll, _portal_client


def test_staff_overview_and_timeline_ordering(
    client, owner_db, make_owner_user, make_tenant
):
    from app.modules.scheduling import service as sched

    b = provision_scheduling(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=f"p360-{uuid.uuid4().hex[:6]}",
        admin_email=f"p360-{uuid.uuid4().hex[:6]}@example.com",
    )
    tid, pid, lid = b["tenant"].id, b["patient"].id, b["location"].id
    start = datetime.now(timezone.utc) + timedelta(days=2)
    appt = sched.create_appointment(
        owner_db,
        tenant_id=tid,
        actor_id=b["admin"].id,
        patient_id=pid,
        practitioner_id=b["practitioner"].id,
        location_id=lid,
        start=start,
        duration_minutes=30,
    )
    owner_db.commit()

    doc = login_client(client, email=b["admin"].email)
    h = tenant_headers(str(tid))

    ov = doc.get(f"/api/v1/tenants/{tid}/patients/{pid}/overview", headers=h)
    assert ov.status_code == 200, ov.text
    body = ov.json()
    assert body["patient_id"] == str(pid)
    assert body["display_name"] == b["patient"].display_name
    assert body["next_appointment_id"] == str(appt.id)
    assert body["outstanding_balance"] is not None
    if body["last_visit_at"] is not None:
        assert body["last_visit_at"].endswith("Z")

    tl = doc.get(f"/api/v1/tenants/{tid}/patients/{pid}/timeline?limit=50", headers=h)
    assert tl.status_code == 200, tl.text
    page = tl.json()
    kinds = [i["kind"] for i in page["items"]]
    assert "patient.registered" in kinds
    assert "appointment.booked" in kinds
    times = [i["occurred_at"] for i in page["items"]]
    assert times == sorted(times, reverse=True)
    assert all(t.endswith("Z") for t in times)

    filtered = doc.get(
        f"/api/v1/tenants/{tid}/patients/{pid}/timeline?category=scheduling",
        headers=h,
    )
    assert filtered.status_code == 200
    assert all(i["category"] == "scheduling" for i in filtered.json()["items"])


def test_timeline_pagination_and_dedupe(
    client, owner_db, make_owner_user, make_tenant
):
    from app.modules.scheduling import service as sched

    b = provision_scheduling(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=f"p360p-{uuid.uuid4().hex[:6]}",
        admin_email=f"p360p-{uuid.uuid4().hex[:6]}@example.com",
    )
    tid, pid, lid = b["tenant"].id, b["patient"].id, b["location"].id
    sched.create_appointment(
        owner_db,
        tenant_id=tid,
        actor_id=b["admin"].id,
        patient_id=pid,
        practitioner_id=b["practitioner"].id,
        location_id=lid,
        start=datetime.now(timezone.utc) + timedelta(days=3),
        duration_minutes=30,
    )
    owner_db.commit()

    doc = login_client(client, email=b["admin"].email)
    h = tenant_headers(str(tid))

    first = doc.get(
        f"/api/v1/tenants/{tid}/patients/{pid}/timeline?limit=1", headers=h
    ).json()
    assert len(first["items"]) == 1
    assert first["next_cursor"]
    second = doc.get(
        f"/api/v1/tenants/{tid}/patients/{pid}/timeline?limit=1"
        f"&cursor={first['next_cursor']}",
        headers=h,
    ).json()
    assert len(second["items"]) == 1
    assert first["items"][0]["event_id"] != second["items"][0]["event_id"]


def test_timeline_tenant_and_patient_isolation(
    client, owner_db, make_owner_user, make_tenant
):
    a = provision_scheduling(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=f"p360a-{uuid.uuid4().hex[:6]}",
        admin_email=f"p360a-{uuid.uuid4().hex[:6]}@example.com",
    )
    b = provision_scheduling(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=f"p360b-{uuid.uuid4().hex[:6]}",
        admin_email=f"p360b-{uuid.uuid4().hex[:6]}@example.com",
    )
    ca = login_client(client, email=a["admin"].email)
    ha = tenant_headers(str(a["tenant"].id))

    r = ca.get(
        f"/api/v1/tenants/{a['tenant'].id}/patients/{b['patient'].id}/timeline",
        headers=ha,
    )
    assert r.status_code == 404
    r2 = ca.get(
        f"/api/v1/tenants/{a['tenant'].id}/patients/{b['patient'].id}/overview",
        headers=ha,
    )
    assert r2.status_code == 404

    r3 = ca.get(
        f"/api/v1/tenants/{b['tenant'].id}/patients/{b['patient'].id}/timeline",
        headers=ha,
    )
    assert r3.status_code in (403, 404)


def test_portal_hides_draft_plans_and_timeline_drafts(
    client, owner_db, make_owner_user, make_tenant
):
    from app.modules.dental import plans as dental_plans

    email = f"portal-p360-{uuid.uuid4().hex[:6]}@example.com"
    b = provision_clinical(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=f"p360d-{uuid.uuid4().hex[:6]}",
        admin_email=f"p360d-{uuid.uuid4().hex[:6]}@example.com",
    )
    _enroll(client, b, email=email)
    tid, pid, act = b["tenant"].id, b["patient"].id, b["admin"].id

    draft = dental_plans.create_plan(
        owner_db,
        tenant_id=tid,
        actor_id=act,
        patient_id=pid,
        practitioner_id=b["practitioner"].id,
        notes="internal draft",
    )
    dental_plans.add_plan_item(
        owner_db,
        tenant_id=tid,
        plan_id=draft.id,
        procedure_code="filling",
        tooth=16,
        sequence=1,
    )
    published = dental_plans.create_plan(
        owner_db,
        tenant_id=tid,
        actor_id=act,
        patient_id=pid,
        practitioner_id=b["practitioner"].id,
        notes="shared plan",
    )
    dental_plans.add_plan_item(
        owner_db,
        tenant_id=tid,
        plan_id=published.id,
        procedure_code="filling",
        tooth=26,
        sequence=1,
    )
    dental_plans.activate_plan(owner_db, tenant_id=tid, plan_id=published.id)
    owner_db.commit()

    ca, ha = _portal_client(client, owner_db, b, email=email)

    plans = ca.get("/api/v1/portal/treatment-plans", headers=ha).json()
    ids = {p["id"] for p in plans}
    assert str(published.id) in ids
    assert str(draft.id) not in ids
    assert (
        ca.get(f"/api/v1/portal/treatment-plans/{draft.id}", headers=ha).status_code
        == 404
    )
    assert (
        ca.get(
            f"/api/v1/portal/treatment-plans/{published.id}", headers=ha
        ).status_code
        == 200
    )

    tl = ca.get("/api/v1/portal/timeline", headers=ha)
    assert tl.status_code == 200, tl.text
    kinds = {i["kind"] for i in tl.json()["items"]}
    assert "treatment_plan.draft" not in kinds
    assert "treatment_plan.published" in kinds
    assert "prescription.draft" not in kinds

    ov = ca.get("/api/v1/portal/overview", headers=ha)
    assert ov.status_code == 200
    assert ov.json()["display_name"] == b["patient"].display_name


def test_portal_timeline_bound_to_link_patient(
    client, owner_db, make_owner_user, make_tenant
):
    """Portal timeline never accepts client patient_id; only the linked patient."""
    a = provision_scheduling(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=f"p360x-{uuid.uuid4().hex[:6]}",
        admin_email=f"p360x-{uuid.uuid4().hex[:6]}@example.com",
    )
    email = f"portal-bound-{uuid.uuid4().hex[:6]}@example.com"
    _enroll(client, a, email=email)
    ca, ha = _portal_client(client, owner_db, a, email=email)

    # Forged query params must be ignored / rejected — no second patient.
    r = ca.get(
        f"/api/v1/portal/timeline?patient_id={uuid.uuid4()}",
        headers=ha,
    )
    assert r.status_code == 200
    # Only this patient's registration event at minimum.
    items = r.json()["items"]
    assert any(i["kind"] == "patient.registered" for i in items)
    assert all(
        i["resource_type"] != "patient" or i["resource_id"] == str(a["patient"].id)
        for i in items
        if i["kind"] == "patient.registered"
    )

    link = (
        owner_db.execute(
            select(PortalLink).where(
                PortalLink.tenant_id == a["tenant"].id, PortalLink.status == "active"
            )
        )
        .scalars()
        .first()
    )
    assert link is not None
    user = owner_db.get(User, link.user_id)
    assert user is not None and user.email == email
