"""Seed a synthetic desktop user for Phase 1.3 local runtime evidence.

Uses OWNER_DATABASE_URL. Password is synthetic and printed once to stdout
for the operator; never written to evidence JSON.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

EMAIL = "desktop.poc@example.com"
PASSWORD = "Desktop-PoC-Only-99zz"
DISPLAY = "Desktop PoC Admin"


def main() -> int:
    url = os.environ.get("OWNER_DATABASE_URL") or os.environ.get("TEST_OWNER_DATABASE_URL")
    if not url:
        print("OWNER_DATABASE_URL missing")
        return 2
    # Load .env lightly
    env_path = ROOT / ".env"
    if env_path.exists() and not os.environ.get("OWNER_DATABASE_URL"):
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("OWNER_DATABASE_URL=") and not line.strip().startswith("#"):
                os.environ["OWNER_DATABASE_URL"] = line.split("=", 1)[1].strip().strip('"')
                url = os.environ["OWNER_DATABASE_URL"]
                break

    from app.modules.clinics import service as clinics_service
    from app.modules.identity import service as identity_service
    from app.modules.subscriptions import service as subscriptions_service
    from app.modules.tenancy import service as tenancy_service

    engine = create_engine(url)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        user = identity_service.get_user_by_email(db, EMAIL)
        if user is None:
            user = identity_service.create_user(
                db, email=EMAIL, display_name=DISPLAY, password=PASSWORD
            )
        else:
            identity_service.set_password(db, user, PASSWORD)
            user.is_active = True
        slug = "desktop-poc"
        tenant = db.execute(
            text("SELECT id FROM tenants WHERE slug = :s"), {"s": slug}
        ).scalar_one_or_none()
        if tenant is None:
            t = tenancy_service.create_tenant(db, name="Desktop PoC Clinic", slug=slug)
            if subscriptions_service.get_subscription(db, tenant_id=t.id) is None:
                subscriptions_service.create_trial_subscription(db, tenant=t)
            clinics_service.create_location(db, tenant=t, name="Main Clinic")
            role = tenancy_service.get_seed_role(db, "tenant_admin")
            tenancy_service.create_membership(
                db, user=user, tenant=t, role=role, is_primary=True
            )
            tenant_id = str(t.id)
        else:
            tenant_id = str(tenant)
            # ensure membership
            role = tenancy_service.get_seed_role(db, "tenant_admin")
            from app.modules.tenancy.models import Membership
            from sqlalchemy import select

            m = db.execute(
                select(Membership).where(
                    Membership.user_id == user.id, Membership.tenant_id == uuid.UUID(tenant_id)
                )
            ).scalar_one_or_none()
            if m is None:
                t = tenancy_service.get_tenant(db, uuid.UUID(tenant_id))
                tenancy_service.create_membership(
                    db, user=user, tenant=t, role=role, is_primary=True
                )
            elif not m.is_active:
                m.is_active = True
        db.commit()
    print(f"email={EMAIL}")
    print(f"password={PASSWORD}")
    print(f"tenant_slug={slug}")
    print(f"tenant_id={tenant_id}")
    print("note=synthetic_only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
