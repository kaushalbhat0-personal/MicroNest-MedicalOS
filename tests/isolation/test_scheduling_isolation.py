"""Scheduling isolation: cross-tenant IDOR, location scope, permission gates,
patient isolation, and audit content safety over HTTP (app role)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from app.platform.time import UTC
from tests.helpers import login_client, provision_scheduling, tenant_headers


def _future_iso(*, days: int = 2) -> str:
    base = datetime.now(UTC) + timedelta(days=days)
    return base.replace(hour=10, minute=0, second=0, microsecond=0).isoformat()


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


def _two(client, owner_db, make_owner_user, make_tenant):  # type: ignore[no-untyped-def]
    a = provision_scheduling(
        owner_db,
        make_owner_user,
        make_tenant,
        slug="sched-iso-a",
        admin_email="sched-a@example.com",
    )
    b = provision_scheduling(
        owner_db,
        make_owner_user,
        make_tenant,
        slug="sched-iso-b",
        admin_email="sched-b@example.com",
    )
    ca = login_client(client, email="sched-a@example.com")
    cb = login_client(client, email="sched-b@example.com")
    return a, b, ca, cb


def test_cross_tenant_appointment_read_is_404(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    a, b, ca, _ = _two(client, owner_db, make_owner_user, make_tenant)
    ha = tenant_headers(a["tenant"].id)
    created = ca.post(
        f"/api/v1/tenants/{a['tenant'].id}/appointments", json=_payload(a), headers=ha
    )
    assert created.status_code == 200, created.text
    aid = created.json()["id"]
    # Tenant-B admin guessing the id under their own scope: 404.
    hb = tenant_headers(b["tenant"].id)
    cb = login_client(client, email="sched-b@example.com")
    assert (
        cb.get(
            f"/api/v1/tenants/{b['tenant'].id}/appointments/{aid}", headers=hb
        ).status_code
        == 404
    )
    # Path-tenant mismatch (B's tenant in A's session): 404.
    assert (
        ca.get(
            f"/api/v1/tenants/{b['tenant'].id}/appointments/{aid}", headers=ha
        ).status_code
        == 404
    )


def test_cross_tenant_creation_with_foreign_refs_is_404(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    a, b, ca, _ = _two(client, owner_db, make_owner_user, make_tenant)
    ha = tenant_headers(a["tenant"].id)
    # A's session, A's path, but B's patient/practitioner/location: fail closed.
    r = ca.post(
        f"/api/v1/tenants/{a['tenant'].id}/appointments",
        json=_payload(
            a,
            patient_id=str(b["patient"].id),
            practitioner_id=str(b["practitioner"].id),
            location_id=str(b["location"].id),
        ),
        headers=ha,
    )
    assert r.status_code == 404, r.text


def test_cross_tenant_patient_read_is_404(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    a, b, ca, _ = _two(client, owner_db, make_owner_user, make_tenant)
    ha = tenant_headers(a["tenant"].id)
    assert (
        ca.get(
            f"/api/v1/tenants/{a['tenant'].id}/patients/{b['patient'].id}", headers=ha
        ).status_code
        == 404
    )


def test_location_scope_denies_other_location(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from app.modules.clinics import service as clinics_service
    from app.modules.tenancy import service as tenancy_service

    b = provision_scheduling(owner_db, make_owner_user, make_tenant, slug="sched-scope")
    loc2 = clinics_service.create_location(owner_db, tenant=b["tenant"], name="Annex")
    owner_db.commit()
    scoped_user = make_owner_user(email="scoped@example.com")
    tenancy_service.create_membership(
        owner_db,
        user=scoped_user,
        tenant=b["tenant"],
        role=tenancy_service.get_seed_role(owner_db, "receptionist"),
        location_ids=[b["location"].id],
    )
    owner_db.commit()
    cc = login_client(client, email="scoped@example.com")
    h = tenant_headers(b["tenant"].id)
    ok = cc.post(
        f"/api/v1/tenants/{b['tenant'].id}/appointments",
        json=_payload(b, location_id=str(b["location"].id)),
        headers=h,
    )
    assert ok.status_code == 200, ok.text
    denied = cc.post(
        f"/api/v1/tenants/{b['tenant'].id}/appointments",
        json=_payload(b, location_id=str(loc2.id), start=_future_iso(days=5)),
        headers=h,
    )
    assert denied.status_code == 403, denied.text


def test_unprivileged_role_denied(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from app.modules.tenancy import service as tenancy_service

    b = provision_scheduling(owner_db, make_owner_user, make_tenant, slug="sched-priv")
    viewer = make_owner_user(email="viewer@example.com")
    tenancy_service.create_membership(
        owner_db,
        user=viewer,
        tenant=b["tenant"],
        role=tenancy_service.get_seed_role(owner_db, "staff"),
    )
    owner_db.commit()
    vc = login_client(client, email="viewer@example.com")
    h = tenant_headers(b["tenant"].id)
    assert (
        vc.post(
            f"/api/v1/tenants/{b['tenant'].id}/appointments",
            json=_payload(b),
            headers=h,
        ).status_code
        == 403
    )
    assert (
        vc.get(f"/api/v1/tenants/{b['tenant'].id}/appointments", headers=h).status_code
        == 403
    )


def test_appointment_notes_never_reach_audit(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import text

    b = provision_scheduling(owner_db, make_owner_user, make_tenant, slug="sched-phi")
    ca = login_client(client, email=b["admin"].email)
    h = tenant_headers(b["tenant"].id)
    marker = "bring-prior-reports-xyz"
    r = ca.post(
        f"/api/v1/tenants/{b['tenant'].id}/appointments",
        json=_payload(b, notes=marker),
        headers=h,
    )
    assert r.status_code == 200, r.text
    rows = owner_db.execute(
        text(
            "SELECT action, reason, resource_id FROM audit_events WHERE tenant_id = :t"
        ),
        {"t": str(b["tenant"].id)},
    ).fetchall()
    assert rows, "scheduling actions must be audited"
    blob = " ".join(str(v) for row in rows for v in row)
    assert marker not in blob
    assert all(
        row[1] is None for row in rows
    ), "no free-text reason on scheduling audit"


def test_rls_blocks_cross_tenant_scheduling_writes_raw_sql(
    app_factory, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    """Defense in depth at the DB layer: the app role cannot write another
    tenant's scheduling rows even with raw SQL."""
    a = provision_scheduling(owner_db, make_owner_user, make_tenant, slug="sched-raw-a")
    b = provision_scheduling(owner_db, make_owner_user, make_tenant, slug="sched-raw-b")

    def scoped(session, tenant_id):  # type: ignore[no-untyped-def]
        session.execute(
            text("SELECT set_config('app.tenant_id', :t, false)"), {"t": str(tenant_id)}
        )

    patient_insert = (
        "INSERT INTO patients (id, tenant_id, display_name, is_active, created_at, updated_at) "
        "VALUES (gen_random_uuid(), :t, 'X', true, now(), now()) RETURNING id"
    )
    appt_insert = (
        "INSERT INTO appointments (id, tenant_id, patient_id, practitioner_id, location_id, "
        "start_at, end_at, timezone, status, created_at, updated_at) "
        "VALUES (gen_random_uuid(), :t, :p, :pr, :l, now() + interval '1 day', "
        "now() + interval '1 day' + interval '30 minutes', "
        "'Asia/Kolkata', 'scheduled', now(), now())"
    )
    with app_factory() as s:
        scoped(s, a["tenant"].id)
        with pytest.raises(Exception):
            s.execute(text(patient_insert), {"t": str(b["tenant"].id)})
            s.commit()
        s.rollback()
        scoped(s, a["tenant"].id)
        pid = s.execute(text(patient_insert), {"t": str(a["tenant"].id)}).fetchone()[0]
        s.execute(
            text(appt_insert),
            {
                "t": str(a["tenant"].id),
                "p": str(pid),
                "pr": str(a["practitioner"].id),
                "l": str(a["location"].id),
            },
        )
        s.commit()
        with pytest.raises(Exception):
            s.execute(
                text(appt_insert),
                {
                    "t": str(b["tenant"].id),
                    "p": str(pid),
                    "pr": str(a["practitioner"].id),
                    "l": str(a["location"].id),
                },
            )
            s.commit()
        s.rollback()
        assert s.execute(text("SELECT count(*) FROM appointments")).scalar_one() >= 1
        s.rollback()


def test_location_scope_enforced_on_reschedule_status_cancel(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    """Scope lives in the service: out-of-scope reschedule/status/cancel fail
    closed (403) while in-scope mutations succeed."""
    from app.modules.clinics import service as clinics_service
    from app.modules.tenancy import service as tenancy_service

    b = provision_scheduling(
        owner_db, make_owner_user, make_tenant, slug="sched-scope-mut"
    )
    loc2 = clinics_service.create_location(owner_db, tenant=b["tenant"], name="Annex")
    owner_db.commit()
    scoped_user = make_owner_user(email="scoped-mut@example.com")
    tenancy_service.create_membership(
        owner_db,
        user=scoped_user,
        tenant=b["tenant"],
        role=tenancy_service.get_seed_role(owner_db, "receptionist"),
        location_ids=[b["location"].id],
    )
    owner_db.commit()
    tid = b["tenant"].id
    admin_c = login_client(client, email=b["admin"].email)
    ha = tenant_headers(tid)
    # Admin books one appointment per location.
    in_scope = admin_c.post(
        f"/api/v1/tenants/{tid}/appointments",
        json=_payload(b, location_id=str(b["location"].id)),
        headers=ha,
    )
    assert in_scope.status_code == 200, in_scope.text
    out_scope = admin_c.post(
        f"/api/v1/tenants/{tid}/appointments",
        json=_payload(b, location_id=str(loc2.id), start=_future_iso(days=5)),
        headers=ha,
    )
    assert out_scope.status_code == 200, out_scope.text
    other_id = out_scope.json()["id"]
    own_id = in_scope.json()["id"]

    cc = login_client(client, email="scoped-mut@example.com")
    h = tenant_headers(tid)
    base = f"/api/v1/tenants/{tid}/appointments/{other_id}"
    assert (
        cc.patch(
            base, json={"start": _future_iso(days=6), "duration_minutes": 30}, headers=h
        ).status_code
        == 403
    )
    assert (
        cc.post(f"{base}/status", json={"status": "confirmed"}, headers=h).status_code
        == 403
    )
    assert cc.post(f"{base}/cancel", json={}, headers=h).status_code == 403
    # In-scope mutations still succeed for the same caller.
    own_base = f"/api/v1/tenants/{tid}/appointments/{own_id}"
    assert (
        cc.patch(
            own_base,
            json={"start": _future_iso(days=6), "duration_minutes": 30},
            headers=h,
        ).status_code
        == 200
    )
    assert (
        cc.post(
            f"{own_base}/status", json={"status": "confirmed"}, headers=h
        ).status_code
        == 200
    )
    assert cc.post(f"{own_base}/cancel", json={}, headers=h).status_code == 200
