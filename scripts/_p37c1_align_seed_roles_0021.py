"""Align global seed roles to exact alembic 0021 ROLE_PERMS.

Completes the incomplete P3.7C repair (which used non-canonical permission
strings). Uses postgres platform role. Does not alter hos_app attributes.
Never prints secrets.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import quote_plus, urlparse, urlunparse

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]

# Exact copy of backend/alembic/versions/0021_inventory.py ROLE_PERMS
CLINICAL_ADMIN = [
    "encounter.open",
    "encounter.close",
    "encounter.read",
    "clinical.read",
    "clinical.create",
    "prescription.read",
    "prescription.create",
    "prescription.sign",
    "dental.read",
    "dental.record",
    "plan.manage",
]
BILLING_FULL = [
    "billing.read",
    "billing.create",
    "invoice.issue",
    "payment.record",
    "billing.refund",
    "billing.config",
]
COMMS = [
    "followup.read",
    "followup.manage",
    "communication.read",
    "communication.log",
    "communication.consent.manage",
]
INV = [
    "inventory.read",
    "inventory.adjust",
    "inventory.manage",
    "inventory.purchase",
]
ROLE_PERMS = {
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
    _, ref = (p.username or "").split(".", 1)
    netloc = (
        f"{quote_plus('postgres.' + ref)}:{quote_plus(p.password or '')}"
        f"@{p.hostname}{(':' + str(p.port)) if p.port else ''}"
    )
    return urlunparse((p.scheme, netloc, p.path, p.params, p.query, p.fragment))


def main() -> int:
    env = load(ROOT / ".env")
    eng = create_engine(as_postgres(env["OWNER_DATABASE_URL_CLOUD"]), pool_pre_ping=True)
    with eng.begin() as c:
        user = c.execute(text("SELECT current_user")).scalar()
        if user != "postgres":
            print(f"STOP expected postgres got {user}")
            return 2
        before = {}
        for row in c.execute(
            text(
                "SELECT name, permissions FROM roles WHERE tenant_id IS NULL ORDER BY name"
            )
        ).mappings():
            before[row["name"]] = sorted(row["permissions"])
        for name, perms in ROLE_PERMS.items():
            target = sorted(set(perms))
            res = c.execute(
                text(
                    "UPDATE roles SET permissions = CAST(:perms AS jsonb) "
                    "WHERE tenant_id IS NULL AND name = :name"
                ),
                {"perms": json.dumps(target), "name": name},
            )
            print(f"align {name} rowcount={res.rowcount} n={len(target)}")
        after = {}
        for row in c.execute(
            text(
                "SELECT name, permissions FROM roles WHERE tenant_id IS NULL ORDER BY name"
            )
        ).mappings():
            after[row["name"]] = sorted(row["permissions"])
        ta = after.get("tenant_admin", [])
        print(
            f"tenant_admin n={len(ta)} plan.manage={'plan.manage' in ta} "
            f"patient.create={'patient.create' in ta} "
            f"billing.refund={'billing.refund' in ta} "
            f"refund.create={'refund.create' in ta}"
        )
        # diff vs intended
        intended = sorted(set(ROLE_PERMS["tenant_admin"]))
        print(f"tenant_admin_matches_0021={ta == intended}")
        removed = sorted(set(before.get("tenant_admin", [])) - set(ta))
        added = sorted(set(ta) - set(before.get("tenant_admin", [])))
        print(f"removed_from_prior_repair={removed}")
        print(f"added_vs_prior={added}")
    print("ALIGN_0021_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
