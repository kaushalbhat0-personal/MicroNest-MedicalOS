"""Seed-role drift guard: migration seeds must equal the permission catalog.

Rationale: `SEED_ROLES` (platform/authz/permissions.py) is the source of
truth for bundles; `0002_tenancy` carries a frozen copy for fresh installs.
If the catalog changes, the migration copy must change with it (new
installs) and a data migration must follow (existing installs).
"""

from app.platform.authz.permissions import SEED_ROLES


def test_seed_roles_match_catalog(owner_db) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import text

    rows = owner_db.execute(
        text("SELECT name, permissions FROM roles WHERE tenant_id IS NULL")
    ).all()
    assert {r[0] for r in rows} == set(SEED_ROLES), "seed role names drifted"
    for name, perms in rows:
        assert sorted(perms) == sorted(SEED_ROLES[name]), f"bundle drift: {name}"
