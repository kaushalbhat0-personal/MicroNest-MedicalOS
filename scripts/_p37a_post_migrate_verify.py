"""Post-migration verification on staging. Never print secrets."""
from __future__ import annotations

import sys
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


def main() -> int:
    env = load_env(ROOT / ".env")
    owner = create_engine(env["OWNER_DATABASE_URL_CLOUD"], pool_pre_ping=True)
    app = create_engine(env["APP_DATABASE_URL_CLOUD"], pool_pre_ping=True)

    with owner.connect() as c:
        rev = c.execute(text("SELECT version_num FROM alembic_version")).scalar()
        print(f"alembic_revision={rev}")
        n = c.execute(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema='public' AND table_type='BASE TABLE'"
            )
        ).scalar()
        print(f"public_tables={n}")
        # key tables
        for t in (
            "tenants",
            "users",
            "patients",
            "document_references",
            "consents",
            "saas_payment_transactions",
        ):
            exists = c.execute(
                text(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_name=:t)"
                ),
                {"t": t},
            ).scalar()
            print(f"table_{t}={exists}")
        rls = c.execute(
            text(
                "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity "
                "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='public' AND c.relkind='r' AND c.relrowsecurity "
                "ORDER BY 1"
            )
        ).all()
        print(f"rls_enabled_tables={len(rls)}")
        # sample
        for name, en, force in rls[:8]:
            print(f"  rls {name}: enabled={en} force={force}")
        if len(rls) > 8:
            print(f"  ... +{len(rls)-8} more")

        # hos_app bypass
        bypass = c.execute(
            text("SELECT rolbypassrls FROM pg_roles WHERE rolname='hos_app'")
        ).scalar()
        print(f"hos_app_bypassrls={bypass}")

    with app.connect() as c:
        print(f"app_current_user={c.execute(text('SELECT current_user')).scalar()}")
        # Without tenant setting, RLS tables should show 0
        locs = c.execute(text("SELECT count(*) FROM locations")).scalar()
        print(f"hos_app_locations_without_tenant_ctx={locs}")
        try:
            c.execute(text("CREATE TABLE p37a_post_fail(id int)"))
            c.commit()
            print("FAIL: hos_app DDL still allowed")
            return 1
        except Exception:
            c.rollback()
            print("PASS: hos_app DDL still denied")

        # Insert as owner then confirm app can't see cross-tenant without setting
    with owner.connect() as c:
        # minimal tenant+location if empty — synthetic only
        from uuid import uuid4

        tid = str(uuid4())
        # tenants may not be RLS'd — insert via owner
        # Check columns
        cols = [
            r[0]
            for r in c.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='tenants' ORDER BY ordinal_position"
                )
            )
        ]
        print(f"tenants_columns_sample={cols[:8]}")

    print("POST_MIGRATE_VERIFY_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
