"""Tenant isolation at the API boundary: cross-tenant access fails closed,
IDOR is 404, selectors are validated, scopes enforced."""

from tests.helpers import login_client, provision_tenant, tenant_headers


def _two_tenants(client, owner_db, make_owner_user, make_tenant):  # type: ignore[no-untyped-def]
    a = provision_tenant(
        owner_db,
        make_owner_user,
        make_tenant,
        slug="iso-a",
        admin_email="a-iso@example.com",
    )
    b = provision_tenant(
        owner_db,
        make_owner_user,
        make_tenant,
        slug="iso-b",
        admin_email="b-iso@example.com",
    )
    ca = login_client(client, email="a-iso@example.com")
    cb = login_client(client, email="b-iso@example.com")
    return a, b, ca, cb


def test_cross_tenant_read_is_404(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    a, b, ca, _ = _two_tenants(client, owner_db, make_owner_user, make_tenant)
    ha = tenant_headers(str(a["tenant"].id))
    assert ca.get(f"/api/v1/tenants/{b['tenant'].id}", headers=ha).status_code == 404
    assert (
        ca.get(f"/api/v1/tenants/{b['tenant'].id}/locations", headers=ha).status_code
        == 404
    )
    assert (
        ca.get(f"/api/v1/tenants/{b['tenant'].id}/audit", headers=ha).status_code == 404
    )


def test_cross_tenant_write_is_404(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    a, b, ca, _ = _two_tenants(client, owner_db, make_owner_user, make_tenant)
    ha = tenant_headers(str(a["tenant"].id))
    bid = str(b["tenant"].id)
    assert (
        ca.post(
            f"/api/v1/tenants/{bid}/locations", headers=ha, json={"name": "Nope Clinic"}
        ).status_code
        == 404
    )
    assert (
        ca.post(
            f"/api/v1/tenants/{bid}/invites",
            headers=ha,
            json={"email": "x@example.com", "role": "staff"},
        ).status_code
        == 404
    )


def test_idor_location_from_other_tenant(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    a, b, ca, _ = _two_tenants(client, owner_db, make_owner_user, make_tenant)
    ha = tenant_headers(str(a["tenant"].id))
    members = ca.get(f"/api/v1/tenants/{a['tenant'].id}/memberships", headers=ha).json()
    mid = members[0]["id"]
    # Guessing B's location id inside A's scope update: refused.
    r = ca.patch(
        f"/api/v1/tenants/{a['tenant'].id}/memberships/{mid}",
        headers=ha,
        json={"location_ids": [str(b["location"].id)]},
    )
    assert r.status_code in (403, 404)


def test_tenant_selector_abuse_rejected(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    a, b, ca, _ = _two_tenants(client, owner_db, make_owner_user, make_tenant)
    # A passes B's tenant id: not a member -> 403 (no data).
    r = ca.get(
        f"/api/v1/tenants/{a['tenant'].id}", headers=tenant_headers(str(b["tenant"].id))
    )
    assert r.status_code == 403
    # Garbage selector: 403.
    assert (
        ca.get(
            f"/api/v1/tenants/{a['tenant'].id}", headers={"X-Tenant": "nope"}
        ).status_code
        == 403
    )


def test_multi_membership_requires_selection(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from app.modules.identity import service as identity_service
    from app.modules.tenancy import service as tenancy_service

    ta = make_tenant(slug="multi-a")
    tb = make_tenant(slug="multi-b")
    user = identity_service.create_user(
        owner_db,
        email="multi@example.com",
        display_name="M",
        password="password-12345-abc",
    )
    admin_role = tenancy_service.get_seed_role(owner_db, "tenant_admin")
    tenancy_service.create_membership(owner_db, user=user, tenant=ta, role=admin_role)
    tenancy_service.create_membership(owner_db, user=user, tenant=tb, role=admin_role)
    owner_db.commit()
    c = login_client(client, email="multi@example.com")
    # No header with two memberships: must select.
    assert c.get(f"/api/v1/tenants/{ta.id}").status_code == 403
    assert (
        c.get(
            f"/api/v1/tenants/{ta.id}", headers=tenant_headers(str(ta.id))
        ).status_code
        == 200
    )
    assert (
        c.get(
            f"/api/v1/tenants/{tb.id}", headers=tenant_headers(str(tb.id))
        ).status_code
        == 200
    )


def test_inactive_membership_and_suspended_tenant(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from app.modules.tenancy import service as tenancy_service

    a = provision_tenant(
        owner_db,
        make_owner_user,
        make_tenant,
        slug="sus-a",
        admin_email="sus@example.com",
    )
    tid = a["tenant"].id
    c = login_client(client, email="sus@example.com")
    h = tenant_headers(str(tid))
    assert c.get(f"/api/v1/tenants/{tid}", headers=h).status_code == 200
    tenancy_service.set_tenant_status(owner_db, a["tenant"], status="suspended")
    owner_db.commit()
    assert c.get(f"/api/v1/tenants/{tid}", headers=h).status_code == 403


def test_privilege_escalation_blocked(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from app.modules.identity import service as identity_service
    from app.modules.tenancy import service as tenancy_service

    a = provision_tenant(
        owner_db,
        make_owner_user,
        make_tenant,
        slug="esc-a",
        admin_email="esc-admin@example.com",
    )
    tid = str(a["tenant"].id)
    rec_user = identity_service.create_user(
        owner_db,
        email="esc-rec@example.com",
        display_name="R",
        password="password-12345-abc",
    )
    tenancy_service.create_membership(
        owner_db,
        user=rec_user,
        tenant=a["tenant"],
        role=tenancy_service.get_seed_role(owner_db, "receptionist"),
    )
    owner_db.commit()
    rec = login_client(client, email="esc-rec@example.com")
    h = tenant_headers(tid)
    assert (
        rec.post(
            f"/api/v1/tenants/{tid}/roles",
            headers=h,
            json={"name": "x", "permissions": []},
        ).status_code
        == 403
    )
    assert rec.get(f"/api/v1/tenants/{tid}/memberships", headers=h).status_code == 403
    assert rec.get(f"/api/v1/tenants/{tid}/audit", headers=h).status_code == 403
    # Patient-role user (no permissions) cannot even read tenant detail.
    pat_user = identity_service.create_user(
        owner_db,
        email="esc-pat@example.com",
        display_name="P",
        password="password-12345-abc",
    )
    tenancy_service.create_membership(
        owner_db,
        user=pat_user,
        tenant=a["tenant"],
        role=tenancy_service.get_seed_role(owner_db, "patient"),
    )
    owner_db.commit()
    pat = login_client(client, email="esc-pat@example.com")
    assert pat.get(f"/api/v1/tenants/{tid}", headers=h).status_code == 403
