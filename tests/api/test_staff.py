"""P1.2 staff directory, invitations, schedules, attendance, leave."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from tests.conftest import TEST_OWNER_URL
from tests.helpers import login_client, provision_tenant, tenant_headers

_PW = "password-12345-abc"


def _setup(owner_db, make_owner_user, make_tenant):
    from app.modules.clinics import service as clinics_service
    from app.modules.identity import service as identity_service
    from app.modules.tenancy import service as tenancy_service

    base = provision_tenant(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=f"staff-{uuid.uuid4().hex[:6]}",
        admin_email=f"staff-admin-{uuid.uuid4().hex[:6]}@example.com",
    )
    nurse = identity_service.create_user(
        owner_db,
        email=f"nurse-{uuid.uuid4().hex[:6]}@example.com",
        display_name="Nurse One",
        password=_PW,
    )
    role = tenancy_service.get_seed_role(owner_db, "nurse")
    nm = tenancy_service.create_membership(
        owner_db, user=nurse, tenant=base["tenant"], role=role
    )
    loc2 = clinics_service.create_location(
        owner_db, tenant=base["tenant"], name="Branch B"
    )
    owner_db.commit()
    return {**base, "nurse": nurse, "nurse_membership": nm, "location2": loc2}


def _auth(client, b, email=None):
    user_email = email or b["admin"].email
    return login_client(client, email=user_email), tenant_headers(str(b["tenant"].id))


def test_staff_directory_and_profile(client, owner_db, make_owner_user, make_tenant):
    b = _setup(owner_db, make_owner_user, make_tenant)
    doc, h = _auth(client, b)
    tid = b["tenant"].id
    listed = doc.get(f"/api/v1/tenants/{tid}/staff", headers=h)
    assert listed.status_code == 200, listed.text
    rows = listed.json()
    assert len(rows) >= 2
    assert any(r["email"] == b["admin"].email for r in rows)
    mid = b["nurse_membership"].id
    patched = doc.patch(
        f"/api/v1/tenants/{tid}/staff/{mid}",
        headers=h,
        json={
            "designation": "Senior Nurse",
            "phone": "+91-9000000000",
            "employment_status": "active",
            "joined_at": "2024-01-15",
            "location_ids": [str(b["location"].id)],
        },
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["designation"] == "Senior Nurse"
    assert body["phone"] == "+91-9000000000"
    assert body["location_ids"] == [str(b["location"].id)]
    assert "patient.read" in body["permissions"]


def test_invite_list_revoke_and_authenticated_accept(
    client, owner_db, make_owner_user, make_tenant
):
    from app.modules.identity import service as identity_service

    b = _setup(owner_db, make_owner_user, make_tenant)
    doc, h = _auth(client, b)
    tid = b["tenant"].id
    email = f"invitee-{uuid.uuid4().hex[:6]}@example.com"
    # Pre-create user so authenticated accept works without shared password flow.
    invitee = identity_service.create_user(
        owner_db,
        email=email,
        display_name="Invitee",
        password=_PW,
    )
    owner_db.commit()

    created = doc.post(
        f"/api/v1/tenants/{tid}/invites",
        headers=h,
        json={
            "email": email,
            "role": "receptionist",
            "location_ids": [str(b["location"].id)],
        },
    )
    assert created.status_code == 200, created.text
    token = created.json()["token"]
    inv_id = created.json()["id"]

    listed = doc.get(f"/api/v1/tenants/{tid}/invitations?status=pending", headers=h)
    assert listed.status_code == 200
    assert any(i["id"] == inv_id for i in listed.json())

    # Revoke then re-create for accept path.
    revoked = doc.post(
        f"/api/v1/tenants/{tid}/invitations/{inv_id}/revoke", headers=h
    )
    assert revoked.status_code == 200
    invitee_client = login_client(client, email=email)
    bad = invitee_client.post(
        "/api/v1/invites/accept-authenticated",
        json={"token": token},
    )
    assert bad.status_code in (409, 410), bad.text

    created2 = doc.post(
        f"/api/v1/tenants/{tid}/invites",
        headers=h,
        json={"email": email, "role": "receptionist"},
    )
    assert created2.status_code == 200, created2.text
    token2 = created2.json()["token"]
    invitee_client = login_client(client, email=invitee.email)
    accepted = invitee_client.post(
        "/api/v1/invites/accept-authenticated",
        json={"token": token2},
    )
    assert accepted.status_code == 200, accepted.text
    # Single-use
    reuse = invitee_client.post(
        "/api/v1/invites/accept-authenticated",
        json={"token": token2},
    )
    assert reuse.status_code in (409, 410)


def test_schedule_attendance_and_duplicate_checkin(
    client, owner_db, make_owner_user, make_tenant
):
    b = _setup(owner_db, make_owner_user, make_tenant)
    doc, h = _auth(client, b)
    tid = b["tenant"].id
    staff_rows = doc.get(f"/api/v1/tenants/{tid}/staff", headers=h).json()
    admin_row = next(r for r in staff_rows if r["email"] == b["admin"].email)
    mid = admin_row["membership_id"]

    sched = doc.post(
        f"/api/v1/tenants/{tid}/staff-schedules",
        headers=h,
        json={
            "membership_id": mid,
            "location_id": str(b["location"].id),
            "weekday": 0,
            "start_time": "09:00:00",
            "end_time": "17:00:00",
            "break_minutes": 60,
            "effective_from": str(date.today()),
        },
    )
    assert sched.status_code == 200, sched.text
    assert sched.json()["weekday"] == 0

    cin = doc.post(
        f"/api/v1/tenants/{tid}/attendance/check-in",
        headers=h,
        json={"location_id": str(b["location"].id)},
    )
    assert cin.status_code == 200, cin.text
    dup = doc.post(
        f"/api/v1/tenants/{tid}/attendance/check-in",
        headers=h,
        json={"location_id": str(b["location"].id)},
    )
    assert dup.status_code == 409, dup.text
    cout = doc.post(
        f"/api/v1/tenants/{tid}/attendance/check-out",
        headers=h,
        json={},
    )
    assert cout.status_code == 200, cout.text
    assert cout.json()["check_out_at"] is not None
    # Invalid second checkout
    again = doc.post(
        f"/api/v1/tenants/{tid}/attendance/check-out",
        headers=h,
        json={},
    )
    assert again.status_code == 409


def test_leave_self_approval_blocked_and_manager_approve(
    client, owner_db, make_owner_user, make_tenant
):
    b = _setup(owner_db, make_owner_user, make_tenant)
    admin_doc, h = _auth(client, b)
    nurse_doc, nh = _auth(client, b, email=b["nurse"].email)
    tid = b["tenant"].id

    types = nurse_doc.get(f"/api/v1/tenants/{tid}/leave-types", headers=nh)
    assert types.status_code == 200, types.text
    lt_id = types.json()[0]["id"]
    req = nurse_doc.post(
        f"/api/v1/tenants/{tid}/leave-requests",
        headers=nh,
        json={
            "leave_type_id": lt_id,
            "start_date": "2026-12-01",
            "end_date": "2026-12-02",
            "reason": "family event",
        },
    )
    assert req.status_code == 200, req.text
    leave_id = req.json()["id"]

    # Nurse cannot approve (no staff.manage)
    denied = nurse_doc.post(
        f"/api/v1/tenants/{tid}/leave-requests/{leave_id}/decide",
        headers=nh,
        json={"decision": "approved"},
    )
    assert denied.status_code == 403

    # Admin self-approval blocked when requesting own leave
    admin_types = admin_doc.get(f"/api/v1/tenants/{tid}/leave-types", headers=h).json()
    own = admin_doc.post(
        f"/api/v1/tenants/{tid}/leave-requests",
        headers=h,
        json={
            "leave_type_id": admin_types[0]["id"],
            "start_date": "2026-12-10",
            "end_date": "2026-12-11",
        },
    )
    assert own.status_code == 200
    self_dec = admin_doc.post(
        f"/api/v1/tenants/{tid}/leave-requests/{own.json()['id']}/decide",
        headers=h,
        json={"decision": "approved"},
    )
    assert self_dec.status_code == 403

    approved = admin_doc.post(
        f"/api/v1/tenants/{tid}/leave-requests/{leave_id}/decide",
        headers=h,
        json={"decision": "approved", "note": "ok"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"


def test_tenant_isolation_staff(client, owner_db, make_owner_user, make_tenant):
    a = _setup(owner_db, make_owner_user, make_tenant)
    b = _setup(owner_db, make_owner_user, make_tenant)
    doc_a, ha = _auth(client, a)
    # A cannot read B staff with A's tenant header against B id
    r = doc_a.get(f"/api/v1/tenants/{b['tenant'].id}/staff", headers=ha)
    assert r.status_code == 404


def test_concurrent_checkin_only_one_succeeds(owner_db, make_owner_user, make_tenant):
    from app.modules.staff import service as staff_svc
    from app.platform.db import make_session_factory
    from app.platform.errors import ConflictError

    b = _setup(owner_db, make_owner_user, make_tenant)
    # Resolve admin membership
    from sqlalchemy import select

    from app.modules.tenancy.models import Membership

    mid = owner_db.execute(
        select(Membership.id).where(
            Membership.tenant_id == b["tenant"].id,
            Membership.user_id == b["admin"].id,
        )
    ).scalar_one()
    owner_db.commit()
    tid = b["tenant"].id
    lid = b["location"].id
    actor = b["admin"].id
    factory = make_session_factory(TEST_OWNER_URL)

    def attempt() -> str:
        s = factory()
        try:
            staff_svc.check_in(
                s,
                tenant_id=tid,
                membership_id=mid,
                location_id=lid,
                actor_user_id=actor,
            )
            s.commit()
            return "ok"
        except ConflictError:
            s.rollback()
            return "conflict"
        finally:
            s.close()

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = [f.result() for f in as_completed([pool.submit(attempt) for _ in range(8)])]
    assert results.count("ok") == 1
    assert results.count("conflict") == 7
