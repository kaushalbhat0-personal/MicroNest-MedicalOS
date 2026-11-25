"""Try creating healthcare_os_preview on Supabase. Never print secrets."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote, urlparse

from sqlalchemy import create_engine, text


def load_env() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in Path(".env").read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def main() -> None:
    env = load_env()
    raw = env["OWNER_DATABASE_URL_CLOUD"].replace(
        "postgresql+psycopg2://", "postgresql://", 1
    )
    u = urlparse(raw)
    pw = quote(env["APP_ROLE_PASSWORD_CLOUD"], safe="")
    ref = env["SUPABASE_PROJECT_REF"]
    # postgres platform role for CREATE DATABASE
    url = (
        f"postgresql+psycopg2://postgres.{ref}:{pw}@{u.hostname}:{u.port or 5432}"
        f"/postgres?sslmode=require"
    )
    eng = create_engine(url, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    with eng.connect() as c:
        print(f"user={c.execute(text('select current_user')).scalar()}")
        exists = c.execute(
            text("SELECT 1 FROM pg_database WHERE datname='healthcare_os_preview'")
        ).scalar()
        print(f"healthcare_os_preview_exists={bool(exists)}")
        if not exists:
            try:
                c.execute(text("CREATE DATABASE healthcare_os_preview OWNER hos_owner"))
                print("CREATE_DATABASE=ok")
            except Exception as exc:  # noqa: BLE001
                print(f"CREATE_DATABASE=fail {type(exc).__name__}")
                # try without owner
                try:
                    c.execute(text("CREATE DATABASE healthcare_os_preview"))
                    print("CREATE_DATABASE_no_owner=ok")
                except Exception as exc2:  # noqa: BLE001
                    print(f"CREATE_DATABASE_no_owner=fail {type(exc2).__name__}")


if __name__ == "__main__":
    main()
