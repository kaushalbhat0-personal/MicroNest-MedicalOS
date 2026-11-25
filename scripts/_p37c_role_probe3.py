"""Probe roles visibility / RLS. No secrets."""
from __future__ import annotations

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
        print("user", c.execute(text("SELECT current_user")).scalar())
        bypass = c.execute(
            text("SELECT rolbypassrls FROM pg_roles WHERE rolname=current_user")
        ).scalar()
        print("bypassrls", bypass)
        rls = c.execute(
            text(
                "SELECT c.relrowsecurity, c.relforcerowsecurity "
                "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='public' AND c.relname='roles'"
            )
        ).first()
        print("roles_rls", rls)
        # Force count as table owner via security barrier? use pg_catalog estimate
        # Try SET row_security = off (requires BYPASSRLS or table owner)
        try:
            c.execute(text("SET row_security = off"))
            n = c.execute(text("SELECT count(*) FROM roles")).scalar()
            print("roles_count_row_security_off", n)
        except Exception as exc:
            print("row_security_off_failed", type(exc).__name__)
            c.rollback()
        # tenants count
        print("tenants", c.execute(text("SELECT count(*) FROM tenants")).scalar())
        print("users", c.execute(text("SELECT count(*) FROM users")).scalar())
        print("memberships", c.execute(text("SELECT count(*) FROM memberships")).scalar())
        # sample membership role_id
        m = c.execute(
            text(
                "SELECT m.id::text, m.role_id::text, t.slug "
                "FROM memberships m JOIN tenants t ON t.id=m.tenant_id LIMIT 5"
            )
        ).all()
        print("membership_sample", m)
        # Try select role by id if we have one
        if m:
            rid = m[0][1]
            try:
                role = c.execute(
                    text("SELECT name, permissions FROM roles WHERE id = CAST(:id AS uuid)"),
                    {"id": rid},
                ).first()
                print("role_by_id", role)
            except Exception as exc:
                print("role_by_id_err", type(exc).__name__, str(exc)[:120])


if __name__ == "__main__":
    main()
