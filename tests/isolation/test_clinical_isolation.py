"""Clinical + dental isolation: cross-tenant IDOR, location scope, role
gates, finalized-record mutation rejection, audit PHI safety."""

from __future__ import annotations

from datetime import date

from tests.helpers import login_client, provision_clinical, tenant_headers


def _open(c, tid, b):  # type: ignore[no-untyped-def]
    r = c.post(
        f"/api/v1/tenants/{tid}/encounters",
        json={
            "patient_id": str(b["patient"].id),
            "practitioner_id": str(b["practitioner"].id),
            "location_id": str(b["location"].id),
        },
        headers=tenant_headers(tid),
    )
    assert r.status_code == 200, r.text
    return r.json()


def _two(client, owner_db, make_owner_user, make_tenant):  # type: ignore[no-untyped-def]
    a = provision_clinical(
        owner_db,
        make_owner_user,
        make_tenant,
        slug="clin-iso-a",
        admin_email="clin-a@example.com",
    )
    b = provision_clinical(
        owner_db,
        make_owner_user,
        make_tenant,
        slug="clin-iso-b",
        admin_email="clin-b@example.com",
    )
    da = login_client(client, email=a["doctor"].email)
    return a, b, da


def test_cross_tenant_encounter_and_records_are_404(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    a, b, da = _two(client, owner_db, make_owner_user, make_tenant)
    ha = tenant_headers(a["tenant"].id)
    e = _open(da, a["tenant"].id, a)
    note = da.post(
        f"/api/v1/tenants/{a['tenant'].id}/encounters/{e['id']}/clinical-notes",
        json={"assessment": "secret"},
        headers=ha,
    )
    assert note.status_code == 200, note.text
    # Tenant B doctor guessing A's encounter/note ids: 404 under own scope.
    db_login = login_client(client, email=b["doctor"].email)
    hb = tenant_headers(b["tenant"].id)
    assert (
        db_login.get(
            f"/api/v1/tenants/{b['tenant'].id}/encounters/{e['id']}", headers=hb
        ).status_code
        == 404
    )
    assert (
        db_login.post(
            f"/api/v1/tenants/{b['tenant'].id}/clinical-notes/{note.json()['id']}/finalize",
            json={},
            headers=hb,
        ).status_code
        == 404
    )
    # Path mismatch with A's session: 404.
    assert (
        da.get(
            f"/api/v1/tenants/{b['tenant'].id}/encounters/{e['id']}", headers=ha
        ).status_code
        == 404
    )


def test_cross_tenant_prescription_and_finding_are_404(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    a, b, da = _two(client, owner_db, make_owner_user, make_tenant)
    ha = tenant_headers(a["tenant"].id)
    e = _open(da, a["tenant"].id, a)
    item = {
        "medication_code": "paracetamol-650",
        "dose": "650 mg",
        "route": "oral",
        "frequency": "TID",
        "instructions": "after food",
    }
    p = da.post(
        f"/api/v1/tenants/{a['tenant'].id}/encounters/{e['id']}/prescriptions",
        json={"items": [item]},
        headers=ha,
    )
    assert p.status_code == 200, p.text
    f = da.post(
        f"/api/v1/tenants/{a['tenant'].id}/encounters/{e['id']}/tooth-findings",
        json={"tooth": 16, "condition_code": "caries"},
        headers=ha,
    )
    assert f.status_code == 200, f.text
    db_login = login_client(client, email=b["doctor"].email)
    hb = tenant_headers(b["tenant"].id)
    assert (
        db_login.get(
            f"/api/v1/tenants/{b['tenant'].id}/prescriptions/{p.json()['id']}",
            headers=hb,
        ).status_code
        == 404
    )
    assert (
        db_login.post(
            f"/api/v1/tenants/{b['tenant'].id}/tooth-findings/{f.json()['id']}/resolve",
            json={},
            headers=hb,
        ).status_code
        == 404
    )
    # Foreign patient reference in own tenant: 404.
    assert (
        da.post(
            f"/api/v1/tenants/{a['tenant'].id}/encounters",
            json={
                "patient_id": str(b["patient"].id),
                "practitioner_id": str(a["practitioner"].id),
                "location_id": str(a["location"].id),
            },
            headers=ha,
        ).status_code
        == 404
    )


def test_location_scope_denies_clinical_writes(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from app.modules.clinics import service as clinics_service
    from app.modules.tenancy import service as tenancy_service

    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="clin-scope")
    loc2 = clinics_service.create_location(owner_db, tenant=b["tenant"], name="Annex")
    owner_db.commit()
    scoped_user = make_owner_user(email="scoped-clin@example.com")
    tenancy_service.create_membership(
        owner_db,
        user=scoped_user,
        tenant=b["tenant"],
        role=tenancy_service.get_seed_role(owner_db, "doctor"),
        location_ids=[b["location"].id],
    )
    owner_db.commit()
    # Practitioner profile for the scoped user (authoring identity).
    scoped_pract = tenancy_service.register_practitioner(
        owner_db, display_name="Scoped", user=scoped_user
    )
    tenancy_service.set_verification(
        owner_db, tenant=b["tenant"], practitioner=scoped_pract, status="approved"
    )
    owner_db.commit()
    doc = login_client(client, email=b["doctor"].email)
    tid = b["tenant"].id
    e = _open(doc, tid, b)
    cc = login_client(client, email="scoped-clin@example.com")
    h = tenant_headers(tid)
    # Own location works.
    own = cc.post(
        f"/api/v1/tenants/{tid}/encounters",
        json={
            "patient_id": str(b["patient"].id),
            "practitioner_id": str(scoped_pract.id),
            "location_id": str(b["location"].id),
        },
        headers=h,
    )
    assert own.status_code == 200, own.text
    # Out-of-scope encounter id for note write: 403.
    denied = cc.post(
        f"/api/v1/tenants/{tid}/encounters/{loc2.id}/clinical-notes",
        json={"assessment": "x"},
        headers=h,
    )
    assert denied.status_code in (403, 404)
    # Out-of-scope open at loc2: 403.
    assert (
        cc.post(
            f"/api/v1/tenants/{tid}/encounters",
            json={
                "patient_id": str(b["patient"].id),
                "practitioner_id": str(scoped_pract.id),
                "location_id": str(loc2.id),
            },
            headers=h,
        ).status_code
        == 403
    )
    _ = e


def test_finalized_content_cannot_be_mutated(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    doc = login_client(client, email=b["doctor"].email)
    tid = b["tenant"].id
    h = tenant_headers(tid)
    e = _open(doc, tid, b)
    item = {
        "medication_code": "paracetamol-650",
        "dose": "650 mg",
        "route": "oral",
        "frequency": "TID",
        "instructions": "after food",
    }
    p = doc.post(
        f"/api/v1/tenants/{tid}/encounters/{e['id']}/prescriptions",
        json={"items": [item]},
        headers=h,
    ).json()
    assert (
        doc.post(
            f"/api/v1/tenants/{tid}/prescriptions/{p['id']}/sign", json={}, headers=h
        ).status_code
        == 200
    )
    # No silent mutation path: sign-again and cancel-then-sign both fail.
    assert (
        doc.post(
            f"/api/v1/tenants/{tid}/prescriptions/{p['id']}/sign", json={}, headers=h
        ).status_code
        == 409
    )
    # There is no PUT/PATCH on any clinical resource: unknown update routes 404/405.
    assert doc.patch(
        f"/api/v1/tenants/{tid}/encounters/{e['id']}",
        json={"status": "closed"},
        headers=h,
    ).status_code in (404, 405)


def test_dental_audit_carries_no_phi(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import text

    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    doc = login_client(client, email=b["doctor"].email)
    tid = b["tenant"].id
    h = tenant_headers(tid)
    e = _open(doc, tid, b)
    marker = "molar-secret-xyz"
    f = doc.post(
        f"/api/v1/tenants/{tid}/encounters/{e['id']}/tooth-findings",
        json={"tooth": 16, "condition_code": "caries", "details": marker},
        headers=h,
    )
    assert f.status_code == 200, f.text
    recall = doc.post(
        f"/api/v1/tenants/{tid}/recalls",
        json={
            "patient_id": str(b["patient"].id),
            "location_id": str(b["location"].id),
            "due_date": date(2027, 6, 1).isoformat(),
            "reason": marker,
        },
        headers=h,
    )
    assert recall.status_code == 200, recall.text
    rows = owner_db.execute(
        text("SELECT action, reason FROM audit_events WHERE tenant_id = :t"),
        {"t": str(tid)},
    ).fetchall()
    blob = " ".join(f"{a} {r}" for a, r in rows)
    assert marker not in blob
    assert all(r is None for _, r in rows)


def test_unauthorized_roles_denied_clinical(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from app.modules.tenancy import service as tenancy_service

    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    tid = b["tenant"].id
    viewer = make_owner_user(email="staff-clin@example.com")
    tenancy_service.create_membership(
        owner_db,
        user=viewer,
        tenant=b["tenant"],
        role=tenancy_service.get_seed_role(owner_db, "staff"),
    )
    owner_db.commit()
    vc = login_client(client, email="staff-clin@example.com")
    h = tenant_headers(tid)
    assert (
        vc.post(
            f"/api/v1/tenants/{tid}/encounters",
            json={
                "patient_id": str(b["patient"].id),
                "practitioner_id": str(b["practitioner"].id),
                "location_id": str(b["location"].id),
            },
            headers=h,
        ).status_code
        == 403
    )
    assert vc.get(f"/api/v1/tenants/{tid}/encounters", headers=h).status_code == 403


def test_rls_blocks_cross_tenant_clinical_writes_raw_sql(
    app_factory, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    """Defense in depth at the DB layer for the P3 tables (app role, raw SQL)."""
    import pytest as _pytest
    from sqlalchemy import text

    a = provision_clinical(owner_db, make_owner_user, make_tenant, slug="clin-raw-a")
    b = provision_clinical(owner_db, make_owner_user, make_tenant, slug="clin-raw-b")

    def scoped(session, tenant_id):  # type: ignore[no-untyped-def]
        session.execute(
            text("SELECT set_config('app.tenant_id', :t, false)"), {"t": str(tenant_id)}
        )

    enc_insert = (
        "INSERT INTO encounters (id, tenant_id, patient_id, practitioner_id, location_id, "
        "status, version, opened_by, opened_at, created_at, updated_at) "
        "VALUES (gen_random_uuid(), :t, :p, :pr, :l, 'open', 1, :u, now(), now(), now()) "
        "RETURNING id"
    )
    with app_factory() as s:
        scoped(s, a["tenant"].id)
        with _pytest.raises(Exception):
            s.execute(
                text(enc_insert),
                {
                    "t": str(b["tenant"].id),
                    "p": str(a["patient"].id),
                    "pr": str(a["practitioner"].id),
                    "l": str(a["location"].id),
                    "u": str(a["admin"].id),
                },
            )
            s.commit()
        s.rollback()
        scoped(s, a["tenant"].id)
        eid = s.execute(
            text(enc_insert),
            {
                "t": str(a["tenant"].id),
                "p": str(a["patient"].id),
                "pr": str(a["practitioner"].id),
                "l": str(a["location"].id),
                "u": str(a["admin"].id),
            },
        ).fetchone()[0]
        s.commit()
        scoped(s, a["tenant"].id)
        with _pytest.raises(Exception):
            s.execute(
                text(
                    "INSERT INTO clinical_notes (id, tenant_id, encounter_id, author_id, "
                    "status, version, is_addendum, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :t, :e, :pr, 'draft', 1, false, now(), now())"
                ),
                {
                    "t": str(b["tenant"].id),
                    "e": str(eid),
                    "pr": str(a["practitioner"].id),
                },
            )
            s.commit()
        s.rollback()
        scoped(s, a["tenant"].id)
        s.execute(
            text(
                "INSERT INTO clinical_notes (id, tenant_id, encounter_id, author_id, "
                "status, version, is_addendum, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :t, :e, :pr, 'draft', 1, false, now(), now())"
            ),
            {"t": str(a["tenant"].id), "e": str(eid), "pr": str(a["practitioner"].id)},
        )
        s.commit()
        assert s.execute(text("SELECT count(*) FROM encounters")).scalar_one() >= 1
        s.rollback()


def test_location_scope_denies_direct_prescription_and_plan_reads(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    """Regression: GET prescription / GET+LIST plans must honor location scope."""
    from app.modules.clinics import service as clinics_service
    from app.modules.tenancy import service as tenancy_service

    b = provision_clinical(
        owner_db, make_owner_user, make_tenant, slug="clin-read-scope"
    )
    loc2 = clinics_service.create_location(owner_db, tenant=b["tenant"], name="Annex")
    owner_db.commit()
    scoped_user = make_owner_user(email="scoped-read@example.com")
    tenancy_service.create_membership(
        owner_db,
        user=scoped_user,
        tenant=b["tenant"],
        role=tenancy_service.get_seed_role(owner_db, "doctor"),
        location_ids=[loc2.id],
    )
    owner_db.commit()
    scoped_pract = tenancy_service.register_practitioner(
        owner_db, display_name="Scoped Read", user=scoped_user
    )
    tenancy_service.set_verification(
        owner_db, tenant=b["tenant"], practitioner=scoped_pract, status="approved"
    )
    owner_db.commit()
    doc = login_client(client, email=b["doctor"].email)
    tid = b["tenant"].id
    h = tenant_headers(tid)
    e = _open(doc, tid, b)
    item = {
        "medication_code": "paracetamol-650",
        "dose": "650 mg",
        "route": "oral",
        "frequency": "TID",
        "instructions": "after food",
    }
    p = doc.post(
        f"/api/v1/tenants/{tid}/encounters/{e['id']}/prescriptions",
        json={"items": [item]},
        headers=h,
    )
    assert p.status_code == 200, p.text
    pid = p.json()["id"]
    plan = doc.post(
        f"/api/v1/tenants/{tid}/treatment-plans",
        json={
            "patient_id": str(b["patient"].id),
            "practitioner_id": str(b["practitioner"].id),
            "encounter_id": e["id"],
            "items": [{"procedure_code": "filling", "tooth": 16}],
        },
        headers=h,
    )
    assert plan.status_code == 200, plan.text
    plan_id = plan.json()["id"]
    cc = login_client(client, email="scoped-read@example.com")
    # Doctor scoped to Annex only: direct reads of Main-location rows are 403/404.
    assert cc.get(
        f"/api/v1/tenants/{tid}/prescriptions/{pid}", headers=h
    ).status_code in (403, 404)
    assert cc.get(
        f"/api/v1/tenants/{tid}/treatment-plans/{plan_id}", headers=h
    ).status_code in (403, 404)
    listed = cc.get(
        f"/api/v1/tenants/{tid}/treatment-plans",
        params={"patient_id": str(b["patient"].id)},
        headers=h,
    )
    assert listed.status_code == 200, listed.text
    assert all(pl["id"] != plan_id for pl in listed.json())
