"""RLS as defense-in-depth, proven with raw SQL as the app role.

These tests bypass the application entirely: even if the app forgot a
tenant filter, the database refuses cross-tenant access.
"""

import pytest
from sqlalchemy import text


def _loc_insert(tenant_id: str) -> object:
    return text(
        "INSERT INTO locations (id, tenant_id, name, timezone, is_active, created_at, updated_at) "
        "VALUES (gen_random_uuid(), :t, 'X', 'UTC', true, now(), now()) RETURNING id"
    )


def test_rls_blocks_cross_tenant_insert(app_factory, owner_db, make_tenant) -> None:  # type: ignore[no-untyped-def]
    ta = make_tenant(slug="rls-a")
    tb = make_tenant(slug="rls-b")

    def scoped(session, tenant_id):  # type: ignore[no-untyped-def]
        # Session-level (not LOCAL): survives ROLLBACK, reset per test session.
        session.execute(
            text("SELECT set_config('app.tenant_id', :t, false)"), {"t": str(tenant_id)}
        )

    with app_factory() as s:
        scoped(s, ta.id)
        with pytest.raises(Exception):
            s.execute(_loc_insert(str(tb.id)), {"t": str(tb.id)})
            s.commit()
        s.rollback()
        scoped(s, ta.id)
        # Same-tenant INSERT works.
        row = s.execute(_loc_insert(str(ta.id)), {"t": str(ta.id)}).fetchone()
        assert row is not None
        s.commit()
        # Cross-tenant UPDATE/DELETE touch 0 rows (fail-closed, no leak).
        assert (
            s.execute(
                text("UPDATE locations SET name='HACK' WHERE tenant_id=:t"),
                {"t": str(tb.id)},
            ).rowcount
            == 0
        )
        assert (
            s.execute(
                text("DELETE FROM locations WHERE tenant_id=:t"), {"t": str(tb.id)}
            ).rowcount
            == 0
        )
        # Own rows remain visible.
        assert s.execute(text("SELECT count(*) FROM locations")).scalar_one() >= 1
        s.rollback()


def test_rls_no_setting_sees_nothing(app_factory, owner_db, make_tenant) -> None:  # type: ignore[no-untyped-def]
    ta = make_tenant(slug="rls-c")
    with app_factory() as s:
        # No app.tenant_id set at all: owned rows invisible, writes fail.
        assert s.execute(text("SELECT count(*) FROM locations")).scalar_one() == 0
        with pytest.raises(Exception):
            s.execute(_loc_insert(str(ta.id)), {"t": str(ta.id)})
            s.commit()
        s.rollback()
