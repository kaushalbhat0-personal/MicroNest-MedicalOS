"""Probe staging roles with shape-only DB URL checks."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]


def load(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def shape(url: str) -> str:
    p = urlparse(url)
    return f"user={p.username} host={p.hostname} db={(p.path or '').lstrip('/')}"


def main() -> None:
    env = load(ROOT / ".env")
    for key in ("OWNER_DATABASE_URL_CLOUD", "APP_DATABASE_URL_CLOUD"):
        print(f"{key}_shape {shape(env[key])}")

    eng = create_engine(env["OWNER_DATABASE_URL_CLOUD"], pool_pre_ping=True)
    with eng.connect() as c:
        print("current_user", c.execute(text("SELECT current_user")).scalar())
        print("db", c.execute(text("SELECT current_database()")).scalar())
        print("alembic", c.execute(text("SELECT version_num FROM alembic_version")).scalar())
        n = c.execute(text("SELECT count(*) FROM roles")).scalar()
        print("roles_count", n)
        names = c.execute(text("SELECT name, count(*) FROM roles GROUP BY name ORDER BY 1")).all()
        print("role_names", names)
        # seed tenant_admin specifically
        row = c.execute(
            text(
                "SELECT name, tenant_id IS NULL AS global_seed, permissions "
                "FROM roles WHERE name='tenant_admin' LIMIT 5"
            )
        ).mappings().all()
        print("tenant_admin_rows", len(row))
        for r in row:
            perms = r["permissions"]
            print(
                "global_seed",
                r["global_seed"],
                "n",
                len(perms or []),
                "patient.create",
                "patient.create" in (perms or []),
            )
            print("perms", sorted(perms or []))


if __name__ == "__main__":
    main()
