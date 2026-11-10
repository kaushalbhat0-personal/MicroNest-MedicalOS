"""P7 evidence for migration 0014 (portal self-read RLS exception).

Proves at the policy level, through the app role (RLS genuinely enforced):
1. A user reads their OWN link with only app.user_id set (no tenant) — the
   workspaces routing signal works before a tenant is selected.
2. The same user cannot read ANOTHER user's link without a tenant selected.
3. A user cannot create a link outside the resolved tenant (WITH CHECK pins
   tenant_id = app.tenant_id) — enrollment stays staff-gated server-side.
4. A user cannot move their link to another tenant (UPDATE blocked).
5. Tenant-scoped reads still work when app.tenant_id is set.
"""

import uuid

import pytest
from sqlalchemy import text

from tests.helpers import login_client, provision_scheduling, tenant_headers


def _enroll(client, base, *, email):  # type: ignore[no-untyped-def]
    admin_client = login_client(client, email=base["admin"].email)
    headers = tenant_headers(str(base["tenant"].id))
    resp = admin_client.post(
        f"/api/v1/tenants/{base['tenant'].id}/portal-links",
        headers=headers,
        json={"email": email, "patient_id": str(base["patient"].id)},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.fixture()
def two_links(client, owner_db, make_owner_user, make_tenant):  # type: ignore[no-untyped-def]
    a = provision_scheduling(
        owner_db,
        make_owner_user,
        make_tenant,
        slug="p7-rls-a",
        admin_email="p7-rls-a@example.com",
    )
    b = provision_scheduling(
        owner_db,
        make_owner_user,
        make_tenant,
        slug="p7-rls-b",
        admin_email="p7-rls-b@example.com",
    )
    _enroll(client, a, email="p7-portal-a@example.com")
    _enroll(client, b, email="p7-portal-b@example.com")
    from app.modules.identity import service as identity_service

    ua = identity_service.get_user_by_email(owner_db, "p7-portal-a@example.com")
    ub = identity_service.get_user_by_email(owner_db, "p7-portal-b@example.com")
    owner_db.commit()
    return {"a": a, "b": b, "ua_id": str(ua.id), "ub_id": str(ub.id)}


def _app_session(app_factory, *, user_id=None, tenant_id=None):  # type: ignore[no-untyped-def]
    session = app_factory()
    session.execute(
        text("SELECT set_config('app.user_id', :u, true)"), {"u": user_id or ""}
    )
    session.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_id or ""}
    )
    return session


def test_self_link_readable_without_tenant(app_factory, two_links) -> None:  # type: ignore[no-untyped-def]
    session = _app_session(app_factory, user_id=two_links["ua_id"])
    try:
        rows = session.execute(
            text("SELECT count(*) FROM portal_links WHERE user_id = :u"),
            {"u": two_links["ua_id"]},
        ).scalar_one()
        assert rows == 1
    finally:
        session.close()


def test_other_link_invisible_without_tenant(app_factory, two_links) -> None:  # type: ignore[no-untyped-def]
    session = _app_session(app_factory, user_id=two_links["ua_id"])
    try:
        rows = session.execute(
            text("SELECT count(*) FROM portal_links WHERE user_id = :u"),
            {"u": two_links["ub_id"]},
        ).scalar_one()
        assert rows == 0
    finally:
        session.close()


def test_insert_outside_resolved_tenant_blocked(app_factory, two_links) -> None:  # type: ignore[no-untyped-def]
    tenant_a = str(two_links["a"]["tenant"].id)
    tenant_b = str(two_links["b"]["tenant"].id)
    session = _app_session(app_factory, user_id=two_links["ua_id"], tenant_id=tenant_a)
    try:
        with pytest.raises(Exception):
            session.execute(
                text(
                    "INSERT INTO portal_links "
                    "(id, tenant_id, user_id, patient_id, created_at) "
                    "VALUES (:id, :t, :u, :p, now())"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "t": tenant_b,  # resolved tenant is A; row claims B
                    "u": two_links["ua_id"],
                    "p": str(two_links["a"]["patient"].id),
                },
            )
            session.commit()
    finally:
        session.rollback()
        session.close()


def test_update_cannot_move_link_across_tenants(app_factory, two_links) -> None:  # type: ignore[no-untyped-def]
    tenant_a = str(two_links["a"]["tenant"].id)
    tenant_b = str(two_links["b"]["tenant"].id)
    session = _app_session(app_factory, user_id=two_links["ua_id"], tenant_id=tenant_a)
    try:
        # WITH CHECK (tenant_id = app.tenant_id) is enforced by Postgres
        # itself: the move raises InsufficientPrivilege, not "0 rows".
        with pytest.raises(Exception, match="[Rr]ow-level security"):
            session.execute(
                text("UPDATE portal_links SET tenant_id = :t WHERE user_id = :u"),
                {"t": tenant_b, "u": two_links["ua_id"]},
            )
            session.commit()
    finally:
        session.rollback()
        session.close()


def test_tenant_scoped_read_still_works(app_factory, two_links) -> None:  # type: ignore[no-untyped-def]
    tenant_a = str(two_links["a"]["tenant"].id)
    session = _app_session(app_factory, user_id=two_links["ua_id"], tenant_id=tenant_a)
    try:
        rows = session.execute(text("SELECT count(*) FROM portal_links")).scalar_one()
        assert rows == 1
    finally:
        session.close()
