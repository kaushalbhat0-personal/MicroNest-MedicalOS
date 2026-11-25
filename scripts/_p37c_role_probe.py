"""Probe staging seed-role permissions. No secrets printed."""
from __future__ import annotations

import json
from pathlib import Path

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


def main() -> None:
    env = load(ROOT / ".env")
    eng = create_engine(env["OWNER_DATABASE_URL_CLOUD"], pool_pre_ping=True)
    with eng.connect() as c:
        rows = c.execute(
            text(
                """
                SELECT id::text AS id, tenant_id::text AS tenant_id, name, is_seed,
                       permissions
                FROM roles
                WHERE name IN ('tenant_admin', 'receptionist', 'doctor')
                ORDER BY name, tenant_id NULLS FIRST
                """
            )
        ).mappings().all()
        print(f"role_rows={len(rows)}")
        for r in rows:
            perms = r["permissions"]
            if isinstance(perms, str):
                perms = json.loads(perms)
            print(
                f"name={r['name']} tenant={r['tenant_id'] or 'NULL'} "
                f"is_seed={r['is_seed']} n={len(perms)} "
                f"patient.create={'patient.create' in perms} "
                f"appointment.create={'appointment.create' in perms} "
                f"staff.manage={'staff.manage' in perms}"
            )
            print(f"  perms={sorted(perms)}")


if __name__ == "__main__":
    main()
