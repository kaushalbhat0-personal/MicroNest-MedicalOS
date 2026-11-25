"""Repair staging global seed-role permissions to match latest Alembic ROLE_PERMS.

Root cause: migrations after FORCE RLS on `roles` ran as `hos_owner` without
BYPASSRLS, so `UPDATE roles … WHERE tenant_id IS NULL` matched 0 rows while
alembic_version still advanced to 0027. Seed roles remain at 0002 baseline
(no patient.create / appointment.create / etc.).

This script:
1. Connects as Supabase `postgres` platform role (BYPASSRLS) using the same
   staging secret material already present locally for cloud roles — never printed.
2. Grants BYPASSRLS to hos_owner only (documented P3.7A recommendation).
3. Re-applies the cumulative seed role permission sets from migration 0021
   (latest ROLE_PERMS that includes inventory + prior clinical/billing/comms).
4. Does NOT touch hos_app privileges or weaken RLS policies.

Refuses to print secrets. Staging-only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import quote_plus, urlparse, urlunparse

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]

# Cumulative seed permissions from alembic 0021_inventory.py ROLE_PERMS
# (latest explicit seed bundle before specialty-only deltas).
CLINICAL_ADMIN = [
    "encounter.open",
    "encounter.close",
    "encounter.read",
    "clinical.create",
    "clinical.read",
    "clinical.amend",
    "prescription.create",
    "prescription.sign",
    "prescription.read",
    "dental.record",
    "dental.read",
]
BILLING_FULL = [
    "billing.read",
    "billing.create",
    "invoice.issue",
    "payment.record",
    "refund.create",
    "credit.allocate",
    "credit.issue_note",
]
COMMS = [
    "followup.read",
    "followup.manage",
    "communication.consent.manage",
    "communication.read",
    "communication.log",
]
INV = ["inventory.read", "inventory.adjust", "inventory.manage"]

ROLE_PERMS: dict[str, list[str]] = {
    "tenant_admin": [
        "tenant.read",
        "settings.manage",
        "staff.invite",
        "staff.manage",
        "roles.manage",
        "locations.manage",
        "audit.read",
        "appointment.read",
        "appointment.create",
        "appointment.update",
        "patient.read",
        "patient.create",
        "patient.update",
        *CLINICAL_ADMIN,
        *BILLING_FULL,
        *COMMS,
        *INV,
    ],
    "doctor": [
        "tenant.read",
        "appointment.read",
        "appointment.update",
        "patient.read",
        *CLINICAL_ADMIN,
        "billing.read",
        "billing.create",
        *COMMS,
        "inventory.read",
        "inventory.adjust",
    ],
    "receptionist": [
        "tenant.read",
        "appointment.read",
        "appointment.create",
        "appointment.update",
        "patient.read",
        "patient.create",
        "patient.update",
        "encounter.open",
        "encounter.read",
        "billing.read",
        "payment.record",
        *COMMS,
        "inventory.read",
        "inventory.adjust",
    ],
    "nurse": [
        "tenant.read",
        "appointment.read",
        "patient.read",
        "encounter.read",
        "clinical.read",
        "clinical.create",
        "followup.read",
        "followup.manage",
        "communication.read",
        "communication.log",
        "inventory.read",
        "inventory.adjust",
    ],
    "accountant": ["tenant.read", *BILLING_FULL, *INV],
    "staff": ["tenant.read"],
    "patient": [
        "portal.read",
        "portal.appointment.cancel",
        "portal.appointment.book",
    ],
    "platform_admin": [
        "platform.tenant.create",
        "platform.tenant.suspend",
        "platform.health",
    ],
}


def load(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def as_postgres(url: str) -> str:
    p = urlparse(url)
    # Session pooler username is role.project_ref
    user = p.username or ""
    if "." not in user:
        raise RuntimeError("expected pooler username role.project_ref")
    _, ref = user.split(".", 1)
    new_user = f"postgres.{ref}"
    # rebuild netloc with same password
    password = p.password or ""
    host = p.hostname or ""
    port = f":{p.port}" if p.port else ""
    netloc = f"{quote_plus(new_user)}:{quote_plus(password)}@{host}{port}"
    return urlunparse((p.scheme, netloc, p.path, p.params, p.query, p.fragment))


def main() -> int:
    env = load(ROOT / ".env")
    owner_url = env["OWNER_DATABASE_URL_CLOUD"]
    pg_url = as_postgres(owner_url)
    parsed = urlparse(pg_url)
    print(f"postgres_user={parsed.username} host={parsed.hostname} db={(parsed.path or '').lstrip('/')}")

    eng = create_engine(pg_url, pool_pre_ping=True)
    try:
        with eng.begin() as c:
            user = c.execute(text("SELECT current_user")).scalar()
            bypass = c.execute(
                text("SELECT rolbypassrls FROM pg_roles WHERE rolname=current_user")
            ).scalar()
            print(f"connected_as={user} bypassrls={bypass}")
            if user != "postgres":
                print("STOP: expected postgres platform role")
                return 2

            # Documented P3.7A ops parity — hos_owner only
            c.execute(text("ALTER ROLE hos_owner BYPASSRLS"))
            print("ALTER ROLE hos_owner BYPASSRLS: ok")

            before = c.execute(
                text(
                    "SELECT name, jsonb_array_length(permissions) "
                    "FROM roles WHERE tenant_id IS NULL ORDER BY name"
                )
            ).all()
            print("seed_roles_before=", before)

            for name, perms in ROLE_PERMS.items():
                res = c.execute(
                    text(
                        "UPDATE roles SET permissions = CAST(:perms AS jsonb) "
                        "WHERE tenant_id IS NULL AND name = :name"
                    ),
                    {"perms": json.dumps(sorted(set(perms))), "name": name},
                )
                print(f"updated name={name} rowcount={res.rowcount}")

            after = c.execute(
                text(
                    "SELECT name, jsonb_array_length(permissions), "
                    "permissions ? 'patient.create' AS has_patient_create "
                    "FROM roles WHERE tenant_id IS NULL ORDER BY name"
                )
            ).all()
            print("seed_roles_after=", after)
    except Exception as exc:
        print(f"FAILED {type(exc).__name__}: {str(exc)[:300]}")
        return 1
    print("SEED_ROLE_REPAIR_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
