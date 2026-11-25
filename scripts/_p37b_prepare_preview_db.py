"""Prepare healthcare_os_preview: grants, migrate, rewrite cloud URLs. No secret prints."""
from __future__ import annotations

import os
import secrets
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote, urlparse, urlunparse

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]


def load_env() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in Path(ROOT / ".env").read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def postgres_url(env: dict[str, str], database: str) -> str:
    raw = env["OWNER_DATABASE_URL_CLOUD"].replace(
        "postgresql+psycopg2://", "postgresql://", 1
    )
    u = urlparse(raw)
    pw = quote(env["APP_ROLE_PASSWORD_CLOUD"], safe="")
    ref = env["SUPABASE_PROJECT_REF"]
    return (
        f"postgresql+psycopg2://postgres.{ref}:{pw}@{u.hostname}:{u.port or 5432}"
        f"/{database}?sslmode=require"
    )


def role_url(env: dict[str, str], role: str, database: str) -> str:
    raw = env["OWNER_DATABASE_URL_CLOUD"].replace(
        "postgresql+psycopg2://", "postgresql://", 1
    )
    u = urlparse(raw)
    pw = quote(env["APP_ROLE_PASSWORD_CLOUD"], safe="")
    ref = env["SUPABASE_PROJECT_REF"]
    return (
        f"postgresql+psycopg2://{role}.{ref}:{pw}@{u.hostname}:{u.port or 5432}"
        f"/{database}?sslmode=require"
    )


def rewrite_env(updates: dict[str, str]) -> None:
    path = ROOT / ".env"
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    out: list[str] = []
    seen: set[str] = set()
    for line in lines:
        written = False
        for k, v in updates.items():
            if line.startswith(f"{k}="):
                out.append(f"{k}={v}\n")
                seen.add(k)
                written = True
                break
        if not written:
            out.append(line if line.endswith("\n") else line + "\n")
    for k, v in updates.items():
        if k not in seen:
            out.append(f"{k}={v}\n")
    path.write_text("".join(out), encoding="utf-8")


def main() -> int:
    env = load_env()
    db = "healthcare_os_preview"
    boot = create_engine(postgres_url(env, "postgres"), pool_pre_ping=True)
    # connect to new db
    eng = create_engine(postgres_url(env, db), pool_pre_ping=True)
    with eng.begin() as c:
        print(f"connected_db={c.execute(text('select current_database()')).scalar()}")
        print(f"user={c.execute(text('select current_user')).scalar()}")
        # ensure roles exist (already on cluster)
        c.execute(text("GRANT CONNECT ON DATABASE healthcare_os_preview TO hos_owner"))
        c.execute(text("GRANT CONNECT ON DATABASE healthcare_os_preview TO hos_app"))
        c.execute(text("GRANT USAGE, CREATE ON SCHEMA public TO hos_owner"))
        c.execute(text("GRANT USAGE ON SCHEMA public TO hos_app"))
        c.execute(text("GRANT hos_owner TO CURRENT_USER"))
        # transfer schema ownership preference
        try:
            c.execute(text("ALTER SCHEMA public OWNER TO hos_owner"))
            print("schema_owner=hos_owner")
        except Exception as exc:  # noqa: BLE001
            print(f"schema_owner_change={type(exc).__name__}")

    owner_url = role_url(env, "hos_owner", db)
    app_url = role_url(env, "hos_app", db)

    # JWT if missing
    jwt = env.get("JWT_SECRET_CLOUD") or ""
    if len(jwt.encode()) < 32:
        jwt = secrets.token_urlsafe(48)
        print("JWT_SECRET_CLOUD=generated")
    else:
        print("JWT_SECRET_CLOUD=retained")

    # Conservative CORS: Render service hostname once created; no invented Vercel URL
    origins = '["https://healthcare-os-api-staging.onrender.com"]'
    print("ALLOWED_ORIGINS_CLOUD=set_to_render_staging_hostname")

    rewrite_env(
        {
            "OWNER_DATABASE_URL_CLOUD": owner_url,
            "APP_DATABASE_URL_CLOUD": app_url,
            "JWT_SECRET_CLOUD": jwt,
            "ALLOWED_ORIGINS_CLOUD": origins,
            "RENDER_API_SERVICE_NAME": "healthcare-os-api-staging",
            "SAAS_PAYMENT_PROVIDER_CLOUD": "mock",
        }
    )
    print("rewrote cloud URLs to database=healthcare_os_preview")

    # migrate
    os.environ["OWNER_DATABASE_URL"] = owner_url
    print("Running alembic upgrade head on healthcare_os_preview...")
    r = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "head"],
        cwd=str(ROOT),
    )
    if r.returncode != 0:
        print("MIGRATE_FAIL")
        return r.returncode

    with create_engine(owner_url, pool_pre_ping=True).connect() as c:
        rev = c.execute(text("SELECT version_num FROM alembic_version")).scalar()
        n = c.execute(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema='public' AND table_type='BASE TABLE'"
            )
        ).scalar()
        print(f"alembic_revision={rev}")
        print(f"public_tables={n}")

    with create_engine(app_url, pool_pre_ping=True).connect() as c:
        print(f"app_user={c.execute(text('select current_user')).scalar()}")
        print(f"app_db={c.execute(text('select current_database()')).scalar()}")
        try:
            c.execute(text("CREATE TABLE p37b_fail(id int)"))
            c.commit()
            print("FAIL ddl")
            return 1
        except Exception:
            c.rollback()
            print("PASS hos_app ddl denied")

    print("PREVIEW_DB_READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
