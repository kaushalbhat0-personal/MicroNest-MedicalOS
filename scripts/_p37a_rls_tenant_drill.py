"""Two-tenant RLS drill on staging (synthetic). Never print secrets."""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]


def load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def postgres_pooler_url(env: dict[str, str]) -> str:
    """Bootstrap DML under FORCE RLS: policies are TO hos_app only; hos_owner
    has no BYPASSRLS on Supabase, so seed inserts use platform postgres role
    (documented staging difference vs local owner bypass)."""
    from urllib.parse import quote, urlparse

    raw = env["OWNER_DATABASE_URL_CLOUD"].replace(
        "postgresql+psycopg2://", "postgresql://", 1
    )
    u = urlparse(raw)
    pw = quote(env["APP_ROLE_PASSWORD_CLOUD"], safe="")
    ref = env["SUPABASE_PROJECT_REF"]
    return (
        f"postgresql+psycopg2://postgres.{ref}:{pw}@{u.hostname}:{u.port or 5432}"
        f"/postgres?sslmode=require"
    )


def main() -> int:
    env = load_env(ROOT / ".env")
    # hos_owner cannot INSERT into FORCE RLS tables without a policy — use postgres for seed.
    bootstrap = create_engine(postgres_pooler_url(env), pool_pre_ping=True)
    app = create_engine(env["APP_DATABASE_URL_CLOUD"], pool_pre_ping=True)

    tid_a = uuid.uuid4()
    tid_b = uuid.uuid4()
    loc_a = uuid.uuid4()
    loc_b = uuid.uuid4()

    with bootstrap.begin() as c:
        print(f"bootstrap_user={c.execute(text('SELECT current_user')).scalar()}")
        for tid, slug, name in (
            (tid_a, f"p37a-a-{tid_a.hex[:8]}", "Synthetic Staging Tenant A"),
            (tid_b, f"p37a-b-{tid_b.hex[:8]}", "Synthetic Staging Tenant B"),
        ):
            c.execute(
                text(
                    "INSERT INTO tenants (id, name, slug, status, created_at, updated_at) "
                    "VALUES (:id, :name, :slug, 'active', now(), now())"
                ),
                {"id": tid, "name": name, "slug": slug},
            )
        for lid, tid, name in (
            (loc_a, tid_a, "Synthetic Loc A"),
            (loc_b, tid_b, "Synthetic Loc B"),
        ):
            c.execute(
                text(
                    "INSERT INTO locations (id, tenant_id, name, timezone, is_active, created_at, updated_at) "
                    "VALUES (:id, :tid, :name, 'UTC', true, now(), now())"
                ),
                {"id": lid, "tid": tid, "name": name},
            )

    with app.connect() as c:
        c.execute(text("SELECT set_config('app.tenant_id', :t, false)"), {"t": str(tid_a)})
        n = c.execute(text("SELECT count(*) FROM locations")).scalar()
        names = [r[0] for r in c.execute(text("SELECT name FROM locations")).all()]
        print(f"app_as_tenant_a_location_count={n} names={names}")
        if n != 1 or names != ["Synthetic Loc A"]:
            print("FAIL: tenant A scope")
            return 1
        # cross update
        upd = c.execute(
            text("UPDATE locations SET name='HACK' WHERE id=:id"),
            {"id": loc_b},
        ).rowcount
        print(f"cross_tenant_update_rowcount={upd}")
        if upd != 0:
            print("FAIL: cross-tenant update")
            return 1
        c.rollback()

    with app.connect() as c:
        c.execute(text("SELECT set_config('app.tenant_id', :t, false)"), {"t": str(tid_b)})
        names = [r[0] for r in c.execute(text("SELECT name FROM locations")).all()]
        print(f"app_as_tenant_b_names={names}")
        if names != ["Synthetic Loc B"]:
            print("FAIL: tenant B scope")
            return 1
        c.rollback()

    # cleanup synthetic rows (postgres bootstrap — FORCE RLS blocks hos_owner DML)
    with bootstrap.begin() as c:
        c.execute(text("DELETE FROM locations WHERE id IN (:a,:b)"), {"a": loc_a, "b": loc_b})
        c.execute(text("DELETE FROM tenants WHERE id IN (:a,:b)"), {"a": tid_a, "b": tid_b})

    print("RLS_TENANT_DRILL_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
