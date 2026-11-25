"""Probe hos_app / hos_owner via Supabase session pooler. Never print secrets."""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import quote, urlparse

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError

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


def pooler_url(env: dict[str, str], role: str) -> str:
    owner = env["OWNER_DATABASE_URL_CLOUD"]
    raw = owner.replace("postgresql+psycopg2://", "postgresql://", 1)
    u = urlparse(raw)
    # password from APP_ROLE_PASSWORD_CLOUD (roles share staging secret for now)
    pw = quote(env["APP_ROLE_PASSWORD_CLOUD"], safe="")
    ref = env["SUPABASE_PROJECT_REF"]
    host = u.hostname
    port = u.port or 5432
    user = f"{role}.{ref}"
    return f"postgresql+psycopg2://{user}:{pw}@{host}:{port}/postgres?sslmode=require"


def main() -> int:
    env = load_env(ROOT / ".env")
    for role in ("hos_owner", "hos_app"):
        url = pooler_url(env, role)
        print(f"=== connect {role} via session pooler ===")
        eng = create_engine(url, pool_pre_ping=True)
        try:
            with eng.connect() as conn:
                print(f"current_user={conn.execute(text('SELECT current_user')).scalar()}")
                print(f"bypassrls={conn.execute(text('SELECT rolbypassrls FROM pg_roles WHERE rolname=current_user')).scalar()}")
                if role == "hos_app":
                    try:
                        conn.execute(text("CREATE TABLE p37a_should_fail (id int)"))
                        conn.commit()
                        print("FAIL: DDL allowed")
                        return 1
                    except ProgrammingError:
                        conn.rollback()
                        print("PASS: DDL denied")
        except OperationalError as exc:
            print(f"FAIL: {type(exc).__name__}")
            # message may contain host; OK. Avoid password.
            msg = str(exc).split("password")[0]
            print(msg[:300])
            return 1
    print("POOLER_ROLE_PROBES_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
