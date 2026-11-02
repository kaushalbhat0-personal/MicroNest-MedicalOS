"""Operational CLI. Explicit jobs only — never runs at web startup.

Usage:
  python -m app.platform.ops bootstrap --email boss@example.com \\
      --tenant-name "Acme Dental" --slug acme-dental --location "Main Clinic"
  python -m app.platform.ops ensure-app-role
"""
from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import text

from app.platform.config import get_settings
from app.platform.db import make_session_factory
from app.platform.logging_setup import configure_root_logging

APP_ROLE = "hos_app"

APP_TABLES = [
    "users",
    "credentials",
    "sessions",
    "password_resets",
    "practitioners",
    "auth_events",
    "tenants",
    "roles",
    "memberships",
    "membership_locations",
    "locations",
    "invitations",
    "practitioner_verifications",
    "audit_events",
    # outbox_events deliberately excluded from app writes via API; the worker
    # uses the same role in P1 (documented exception, internal-only table).
    "outbox_events",
]


def _owner_factory():  # type: ignore[no-untyped-def]
    settings = get_settings()
    if not settings.OWNER_DATABASE_URL:
        raise RuntimeError("OWNER_DATABASE_URL is not configured")
    return make_session_factory(settings.OWNER_DATABASE_URL)


def cmd_ensure_app_role() -> None:
    from app.platform.config import get_settings as gs

    settings = gs()
    if not settings.APP_ROLE_PASSWORD:
        raise RuntimeError("APP_ROLE_PASSWORD is not configured")
    factory = _owner_factory()
    with factory() as session:
        session.execute(text(f"DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN CREATE ROLE {APP_ROLE} LOGIN PASSWORD :pwd; END IF; END $$;").bindparams(pwd=settings.APP_ROLE_PASSWORD))  # noqa: E501
        session.execute(text("GRANT USAGE ON SCHEMA public TO hos_app"))
        for table in APP_TABLES:
            session.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO hos_app"))
        session.execute(text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO hos_app"))
        session.commit()
    print(f"app role '{APP_ROLE}' ensured")


def cmd_bootstrap(args: argparse.Namespace) -> None:
    from app.modules.identity import service as identity_service
    from app.modules.tenancy import service as tenancy_service

    factory = _owner_factory()
    with factory() as session:
        with session.begin():
            email = identity_service.normalize_email(args.email)
            existing = identity_service.get_user_by_email(session, email)
            if existing is not None:
                raise RuntimeError("user already exists; use invites for more admins")
            user = identity_service.create_user(
                session, email=email, display_name=args.name or email, password=None
            )
            user.is_platform_admin = True
            tenant = tenancy_service.create_tenant(
                session, name=args.tenant_name, slug=args.slug
            )
            from app.modules.clinics import service as clinics_service

            clinics_service.create_location(
                session, tenant=tenant, name=args.location
            )
            role = tenancy_service.get_seed_role(session, "tenant_admin")
            tenancy_service.create_membership(
                session, user=user, tenant=tenant, role=role, is_primary=True
            )
            identity_service.record_auth_event(
                session, action="bootstrap", user_id=user.id, tenant_id=tenant.id
            )
        with session.begin():
            raw = identity_service.create_password_reset(session, user)
    print(f"tenant: {tenant.slug} ({tenant.id})")
    print(f"platform admin: {user.email}")
    print("Single-use password setup token (expires in 2h):")
    print(raw)


def main(argv: list[str] | None = None) -> int:
    configure_root_logging()
    parser = argparse.ArgumentParser(prog="ops")
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bootstrap")
    b.add_argument("--email", required=True)
    b.add_argument("--tenant-name", required=True)
    b.add_argument("--slug", required=True)
    b.add_argument("--location", required=True)
    b.add_argument("--name", default="")
    sub.add_parser("ensure-app-role")
    args = parser.parse_args(argv)
    if args.cmd == "bootstrap":
        cmd_bootstrap(args)
    elif args.cmd == "ensure-app-role":
        cmd_ensure_app_role()
    return 0


if __name__ == "__main__":
    sys.exit(main())
