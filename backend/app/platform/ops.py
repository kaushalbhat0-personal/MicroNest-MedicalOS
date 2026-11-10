"""Operational CLI. Explicit jobs only — never runs at web startup.

Usage:
  python -m app.platform.ops bootstrap --email boss@example.com \\
      --tenant-name "Acme Dental" --slug acme-dental --location "Main Clinic"
  python -m app.platform.ops ensure-app-role
"""

from __future__ import annotations

import argparse
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
    "email_verifications",
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
    # O1.2a: ownership, trial subscription catalog + rows, specialty
    # enablement, provisioning idempotency ledger.
    "tenant_owners",
    "subscription_plans",
    "subscriptions",
    "tenant_specialties",
    "workspace_provisions",
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
        # Migration 0005 owns role creation (NOLOGIN, no secrets in history).
        # This job only enables login + ensures grants (idempotent).
        session.execute(
            text(
                "DO $$ BEGIN IF NOT EXISTS "
                "(SELECT FROM pg_roles WHERE rolname = 'hos_app') "
                "THEN CREATE ROLE hos_app NOLOGIN; END IF; END $$;"
            )
        )
        session.execute(
            text("ALTER ROLE hos_app WITH LOGIN PASSWORD :pwd").bindparams(
                pwd=settings.APP_ROLE_PASSWORD
            )
        )
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
            tenant = tenancy_service.create_tenant(session, name=args.tenant_name, slug=args.slug)
            from app.modules.clinics import service as clinics_service

            clinics_service.create_location(session, tenant=tenant, name=args.location)
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


def cmd_check_readiness() -> int:
    """Operator readiness probe: config + DB + storage + notify status.

    Prints only variable names and coarse statuses — never secret values,
    connection strings, or PHI. Exit 0 when the instance may serve traffic.
    """
    import uuid

    from app.platform.config import validate_for_boot

    settings = get_settings()
    problems = validate_for_boot(settings)
    if problems:
        print("configuration: INVALID")
        for problem in problems:
            print(f"  - {problem}")
        return 2
    print(f"configuration: ok (ENV={settings.ENV} DEPLOYMENT={settings.DEPLOYMENT})")

    if not settings.APP_DATABASE_URL:
        print("database: not-configured")
        return 2
    try:
        factory = make_session_factory(settings.APP_DATABASE_URL)
        with factory() as session:
            session.execute(text("SELECT 1"))
    except Exception:
        print("database: unreachable")
        return 1
    print("database: reachable")

    strict = settings.ENV in ("preview", "prod", "production")
    try:
        from app.platform.adapters.s3_storage import build_storage_adapter

        adapter = build_storage_adapter(settings)
        probe = f"_ops/probe-{uuid.uuid4().hex}"
        adapter.put(key=probe, data=b"probe", content_type="text/plain")
        assert adapter.exists(key=probe)
        assert adapter.get(key=probe) == b"probe"
        adapter.delete(key=probe)
        print(f"storage: ok ({settings.STORAGE_ADAPTER})")
    except Exception as exc:
        print(f"storage: unavailable ({type(exc).__name__})")
        if strict:
            return 1

    from app.platform.adapters.notify import build_notify_adapter

    notify = build_notify_adapter(settings)
    print(f"notify: provider={notify.name} healthy={notify.health()}")
    if notify.health() is False and settings.NOTIFY_PROVIDER != "none":
        print("notify: no healthy provider configured")
    return 0


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
    sub.add_parser("check-readiness")
    args = parser.parse_args(argv)
    if args.cmd == "bootstrap":
        cmd_bootstrap(args)
    elif args.cmd == "ensure-app-role":
        cmd_ensure_app_role()
    elif args.cmd == "check-readiness":
        return cmd_check_readiness()
    return 0


if __name__ == "__main__":
    sys.exit(main())
