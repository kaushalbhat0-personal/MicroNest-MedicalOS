"""Ensure desktop-poc tenant has an approved practitioner for M5/M6 evidence."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


def _load_owner_url() -> str:
    url = os.environ.get("OWNER_DATABASE_URL")
    if url:
        return url
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("OWNER_DATABASE_URL=") and not line.strip().startswith("#"):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("OWNER_DATABASE_URL missing")


def main() -> int:
    from app.modules.tenancy import service as tenancy_service
    from app.modules.tenancy.models import Tenant, Verification

    engine = create_engine(_load_owner_url())
    Session = sessionmaker(bind=engine)
    with Session() as db:
        tenant = db.execute(select(Tenant).where(Tenant.slug == "desktop-poc")).scalar_one()
        existing = db.execute(
            select(Verification).where(
                Verification.tenant_id == tenant.id,
                Verification.status == "approved",
            )
        ).scalars().first()
        if existing:
            print(f"already_approved practitioner={existing.practitioner_id}")
            return 0
        prac = tenancy_service.register_practitioner(db, display_name="Dr Desktop PoC")
        tenancy_service.set_verification(
            db, tenant=tenant, practitioner=prac, status="approved"
        )
        db.commit()
        print(f"approved practitioner={prac.id} tenant={tenant.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
