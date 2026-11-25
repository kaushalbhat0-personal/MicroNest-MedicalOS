"""Inspect/create hos_owner + hos_app on Supabase staging. Never print secrets."""
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
    owner_url = env.get("OWNER_DATABASE_URL_CLOUD", "")
    app_pw = env.get("APP_ROLE_PASSWORD_CLOUD", "")
    if not owner_url:
        print("MISSING: OWNER_DATABASE_URL_CLOUD")
        return 2
    if not app_pw:
        print("MISSING: APP_ROLE_PASSWORD_CLOUD")
        return 2

    eng = create_engine(owner_url, pool_pre_ping=True)
    with eng.connect() as conn:
        ver = conn.execute(text("SHOW server_version")).scalar()
        print(f"connected_as={conn.execute(text('SELECT current_user')).scalar()}")
        print(f"db={conn.execute(text('SELECT current_database()')).scalar()}")
        print(f"server_version={ver}")

        roles = conn.execute(
            text(
                "SELECT rolname, rolsuper, rolbypassrls, rolcanlogin, rolcreaterole, rolcreatedb "
                "FROM pg_roles WHERE rolname IN ('postgres','hos_owner','hos_app','authenticator','service_role') "
                "ORDER BY rolname"
            )
        ).mappings().all()
        print("=== roles of interest ===")
        for r in roles:
            print(
                f"- {r['rolname']}: super={r['rolsuper']} bypassrls={r['rolbypassrls']} "
                f"login={r['rolcanlogin']} createrole={r['rolcreaterole']} createdb={r['rolcreatedb']}"
            )

        tables = conn.execute(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema='public' AND table_type='BASE TABLE'"
            )
        ).scalar()
        print(f"public_base_tables={tables}")

        alembic = conn.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name='alembic_version')"
            )
        ).scalar()
        print(f"alembic_version_table={alembic}")
        if alembic:
            rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            print(f"alembic_revision={rev}")

        exts = conn.execute(
            text("SELECT extname FROM pg_extension ORDER BY 1")
        ).scalars().all()
        print(f"extensions={list(exts)}")

        # Create roles if missing (no BYPASSRLS on hos_app).
        print("=== ensure hos_owner / hos_app ===")
        conn.execute(
            text(
                """
                DO $$ BEGIN
                  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'hos_owner') THEN
                    CREATE ROLE hos_owner NOLOGIN;
                  END IF;
                  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'hos_app') THEN
                    CREATE ROLE hos_app NOLOGIN NOBYPASSRLS;
                  END IF;
                END $$;
                """
            )
        )
        # Enable login + set passwords from APP_ROLE_PASSWORD_CLOUD for hos_app.
        # hos_owner password: reuse APP_ROLE_PASSWORD_CLOUD for staging bootstrap only
        # (document as shared-secret risk); prefer separate secrets later.
        conn.execute(
            text("ALTER ROLE hos_owner WITH LOGIN PASSWORD :pwd").bindparams(pwd=app_pw)
        )
        conn.execute(
            text("ALTER ROLE hos_app WITH LOGIN PASSWORD :pwd NOBYPASSRLS").bindparams(
                pwd=app_pw
            )
        )
        # Schema privileges for migration ownership parity
        conn.execute(text("GRANT USAGE, CREATE ON SCHEMA public TO hos_owner"))
        conn.execute(text("GRANT USAGE ON SCHEMA public TO hos_app"))
        # Allow hos_owner to manage objects created by current migrator if needed
        conn.execute(text("GRANT hos_owner TO CURRENT_USER"))
        conn.commit()

        # Re-read role flags
        for name in ("hos_owner", "hos_app"):
            r = conn.execute(
                text(
                    "SELECT rolsuper, rolbypassrls, rolcanlogin FROM pg_roles WHERE rolname=:n"
                ),
                {"n": name},
            ).mappings().one()
            print(
                f"ensured {name}: super={r['rolsuper']} bypassrls={r['rolbypassrls']} "
                f"login={r['rolcanlogin']}"
            )

        # App role DDL probe (should fail for CREATE TABLE)
        print("=== hos_app DDL probe ===")
        from sqlalchemy.exc import ProgrammingError

        app_url = owner_url
        # Build hos_app URL from OWNER pooler host but swap user — prefer direct for role tests
        # Use APP url host if direct postgres, else derive from SUPABASE_PROJECT_REF
        ref = env["SUPABASE_PROJECT_REF"]
        # Direct connection as hos_app
        # Parse password from env only — do not print
        direct = (
            f"postgresql+psycopg2://hos_app:{app_pw}"
            f"@db.{ref}.supabase.co:5432/postgres?sslmode=require"
        )
        app_eng = create_engine(direct, pool_pre_ping=True)
        try:
            with app_eng.connect() as ac:
                print(f"hos_app_connected_as={ac.execute(text('SELECT current_user')).scalar()}")
                try:
                    ac.execute(text("CREATE TABLE p37a_should_fail (id int)"))
                    ac.commit()
                    print("FAIL: hos_app was able to CREATE TABLE")
                    return 1
                except ProgrammingError:
                    ac.rollback()
                    print("PASS: hos_app cannot CREATE TABLE (expected)")
                # bypass check
                bypass = ac.execute(
                    text("SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user")
                ).scalar()
                print(f"hos_app_rolbypassrls={bypass}")
                if bypass:
                    print("FAIL: hos_app has BYPASSRLS")
                    return 1
                print("PASS: hos_app NOBYPASSRLS")
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL: hos_app direct connect: {type(exc).__name__}: {exc}")
            return 1

    print("ROLE_SETUP_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
