"""Link desktop.poc user to an approved practitioner so clinical writes work.

Clinical notes/Rx use practitioner_for_user(ctx) — the actor must have a linked
practitioner profile. Synthetic only.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

EMAIL = "desktop.poc@example.com"


def _load_owner_url() -> str:
    url = os.environ.get("OWNER_DATABASE_URL")
    if url:
        return url
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("OWNER_DATABASE_URL=") and not line.strip().startswith("#"):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("OWNER_DATABASE_URL missing")


def main() -> int:
    from app.modules.identity.models import Practitioner, User
    from app.modules.tenancy import service as tenancy_service
    from app.modules.tenancy.models import Tenant

    engine = create_engine(_load_owner_url())
    Session = sessionmaker(bind=engine)
    with Session() as db:
        user = db.execute(select(User).where(User.email == EMAIL)).scalar_one()
        tenant = db.execute(select(Tenant).where(Tenant.slug == "desktop-poc")).scalar_one()
        linked = db.execute(
            select(Practitioner).where(Practitioner.user_id == user.id)
        ).scalar_one_or_none()
        if linked is None:
            linked = tenancy_service.register_practitioner(
                db, display_name="Dr Desktop PoC Linked", user=user
            )
            print(f"created_linked practitioner={linked.id}")
        else:
            print(f"already_linked practitioner={linked.id}")
        tenancy_service.set_verification(
            db, tenant=tenant, practitioner=linked, status="approved"
        )
        db.commit()
        print(f"approved for tenant={tenant.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
