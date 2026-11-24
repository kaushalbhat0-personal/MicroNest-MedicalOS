"""P1 test harness. Real PostgreSQL only (embedded pgserver binary when
DATABASE_URL_TEST is unset; CI provides a service Postgres instead).

Per-session: fresh schema + alembic upgrade head on the TEST database.
Per-test: TRUNCATE ... CASCADE for isolation.
The API runs through the app-role factory so RLS is genuinely exercised.
"""

import os
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

TEST_OWNER_URL = os.environ.get(
    "TEST_OWNER_DATABASE_URL",
    "postgresql+psycopg2://hos_owner:owner-dev-pass@127.0.0.1:5432/healthcare_os_test",
)
TEST_APP_URL = os.environ.get(
    "TEST_APP_DATABASE_URL",
    "postgresql+psycopg2://hos_app:change-me-app-role@127.0.0.1:5432/healthcare_os_test",
)

os.environ.setdefault("JWT_SECRET", "test-only-secret-min-32-chars-xxxxxxxx")
os.environ.setdefault("ENV", "test")
os.environ.setdefault("DEV_NOTIFICATIONS_ALLOW", "true")

from app import main as main_module  # noqa: E402
from app.api import deps as deps_module  # noqa: E402
from app.api.deps import get_db  # noqa: E402
from app.modules.identity import service as identity_service  # noqa: E402
from app.modules.tenancy import service as tenancy_service  # noqa: E402
from app.platform import db as dbmod  # noqa: E402
from app.platform.ratelimit import limiter  # noqa: E402

ALL_TABLES = [
    "audit_events",
    "auth_events",
    "clinical_notes",
    "consents",
    "credit_notes",
    "credentials",
    "dental_procedure_records",
    "document_references",
    "encounter_diagnoses",
    "encounters",
    "email_verifications",
    "estimate_lines",
    "estimates",
    "follow_ups",
    "communication_logs",
    "communication_consents",
    "goods_receipt_lines",
    "goods_receipts",
    "purchase_order_lines",
    "purchase_orders",
    "inventory_movements",
    "inventory_balances",
    "inventory_suppliers",
    "inventory_items",
    "invitations",
    "invoice_lines",
    "invoices",
    "leave_requests",
    "leave_types",
    "attendance_records",
    "staff_schedules",
    "staff_profiles",
    "locations",
    "location_working_hours",
    "membership_locations",
    "memberships",
    "observations",
    "outbox_events",
    "password_resets",
    "payment_allocations",
    "payments",
    "portal_links",
    "practitioner_verifications",
    "practitioners",
    "prescription_items",
    "prescriptions",
    "receipts",
    "recalls",
    "refunds",
    "roles",
    "sessions",
    "tenants",
    "tenant_owners",
    "tenant_specialties",
    "subscription_events",
    "subscription_plans",
    "subscriptions",
    "saas_customers",
    "saas_payment_transactions",
    "saas_webhook_inbox",
    "workspace_provisions",
    "tooth_finding_surfaces",
    "tooth_findings",
    "treatment_plan_items",
    "treatment_plans",
    "users",
    "patients",
    "appointments",
]
# Global read-only catalogs (observation_types, diagnosis_codes, medications,
# dental_conditions, dental_procedures, service_catalog) are seeded by
# migrations and never truncated: no write endpoint exists, so tests cannot
# dirty them.


def _owner_factory():  # type: ignore[no-untyped-def]
    return dbmod.make_session_factory(TEST_OWNER_URL)


@pytest.fixture(scope="session")
def migrated_db() -> Iterator[None]:
    from sqlalchemy import create_engine, text

    previous = os.environ.get("OWNER_DATABASE_URL")
    os.environ["OWNER_DATABASE_URL"] = TEST_OWNER_URL
    try:
        engine = create_engine(TEST_OWNER_URL)
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
            conn.execute(text("GRANT ALL ON SCHEMA public TO hos_owner"))
        engine.dispose()
        from alembic import command
        from alembic.config import Config

        cfg = Config("backend/alembic.ini")
        command.upgrade(cfg, "head")
        # Migration 0005 creates hos_app NOLOGIN (no secrets in migrations).
        # Tests and dev enable login with the environment password here —
        # the single place credentials meet the role (CI supplies its own).
        app_pw = os.environ.get("TEST_APP_ROLE_PASSWORD", "change-me-app-role")
        engine2 = create_engine(TEST_OWNER_URL, isolation_level="AUTOCOMMIT")
        with engine2.begin() as conn:
            conn.execute(
                text("ALTER ROLE hos_app WITH LOGIN PASSWORD :pwd"), {"pwd": app_pw}
            )
        engine2.dispose()
    finally:
        if previous is None:
            del os.environ["OWNER_DATABASE_URL"]
        else:
            os.environ["OWNER_DATABASE_URL"] = previous
    yield


@pytest.fixture()
def owner_db(migrated_db: None):  # type: ignore[no-untyped-def]
    factory = _owner_factory()
    with factory() as session:
        session.execute(text(f"TRUNCATE {', '.join(ALL_TABLES)} CASCADE"))
        session.commit()
        # Re-seed roles (truncate wiped them) to match migration state.
        from datetime import datetime, timezone

        from app.platform.authz.permissions import SEED_ROLES

        now = datetime.now(timezone.utc)
        import json

        # Seed roles use tenant_id NULL; Postgres UNIQUE (tenant_id, name) does
        # not collapse NULLs, so wipe before re-insert to avoid duplicates across
        # tests (and across interrupted parallel runs).
        session.execute(
            text("DELETE FROM roles WHERE tenant_id IS NULL AND is_seed IS TRUE")
        )
        for name, perms in SEED_ROLES.items():
            session.execute(
                text(
                    "INSERT INTO roles (id, tenant_id, name, permissions, is_seed, created_at) "
                    "VALUES (gen_random_uuid(), NULL, :name, :perms, true, :now)"
                ),
                {"name": name, "perms": json.dumps(sorted(perms)), "now": now},
            )
        # Re-seed the trial plan catalog (truncate wiped migration 0016's
        # seed row). Values mirror 0016 exactly: trial-only, unenforced.
        session.execute(
            text(
                "INSERT INTO subscription_plans "
                "(id, code, name, family_code, version, description, currency, "
                " billing_interval, price_minor, features, "
                " max_locations, max_practitioners, max_staff_seats, "
                " trial_days, is_active, created_at, updated_at) "
                "VALUES "
                "(gen_random_uuid(), 'trial-14d', 'Trial (14-day)', 'trial-14d', 1, "
                " '14-day trial', 'INR', NULL, 0, CAST(:feat AS JSONB), "
                " 3, 10, 25, 14, true, :now, :now), "
                "(gen_random_uuid(), 'starter-v1', 'Starter', 'starter', 1, "
                " 'Starter catalog', 'INR', 'month', 499900, CAST(:feat AS JSONB), "
                " 1, 5, 15, 0, true, :now, :now), "
                "(gen_random_uuid(), 'growth-v1', 'Growth', 'growth', 1, "
                " 'Growth catalog', 'INR', 'month', 999900, CAST(:feat AS JSONB), "
                " 5, 25, 50, 0, true, :now, :now) "
                "ON CONFLICT (code) DO NOTHING"
            ),
            {
                "now": now,
                "feat": (
                    '{"patient_portal": true, "inventory": false, '
                    '"operations_dashboard": true, "clinic_billing": true, '
                    '"staff_workforce": false, "informational_limits": true}'
                ),
            },
        )
        # Trial: all enforced features on for evaluation (P2.3).
        session.execute(
            text(
                "UPDATE subscription_plans SET features = CAST(:feat AS JSONB) "
                "WHERE code = 'trial-14d'"
            ),
            {
                "feat": (
                    '{"patient_portal": true, "inventory": true, '
                    '"operations_dashboard": true, "clinic_billing": true, '
                    '"staff_workforce": true, "informational_limits": true}'
                ),
            },
        )
        # Growth catalog features (inventory + staff_workforce).
        session.execute(
            text(
                "UPDATE subscription_plans SET features = CAST(:feat AS JSONB) "
                "WHERE code = 'growth-v1'"
            ),
            {
                "feat": (
                    '{"patient_portal": true, "inventory": true, '
                    '"operations_dashboard": true, "clinic_billing": true, '
                    '"staff_workforce": true, "informational_limits": true}'
                ),
            },
        )
        session.commit()
        yield session


@pytest.fixture()
def app_factory():  # type: ignore[no-untyped-def]
    return dbmod.make_session_factory(TEST_APP_URL)


@pytest.fixture()
def client(app_factory, owner_db):  # type: ignore[no-untyped-def]
    limiter._hits.clear()
    deps_module._factory = app_factory

    def _test_db():  # type: ignore[no-untyped-def]
        with dbmod.scoped_transaction(app_factory) as session:
            yield session

    app = main_module.create_app()
    app.dependency_overrides[get_db] = _test_db
    with TestClient(app, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    deps_module._factory = None
    dbmod.tenant_ctx.set(None)
    dbmod.actor_ctx.set(None)


@pytest.fixture()
def make_owner_user(owner_db):  # type: ignore[no-untyped-def]
    n = {"i": 0}

    def _make(
        *, email: str | None = None, password: str = "password-12345-abc"
    ) -> object:
        n["i"] += 1
        user = identity_service.create_user(
            owner_db,
            email=email or f"user{n['i']}-{uuid.uuid4().hex[:6]}@example.com",
            display_name=f"User {n['i']}",
            password=password,
        )
        owner_db.commit()
        return user

    return _make


@pytest.fixture()
def make_tenant(owner_db):  # type: ignore[no-untyped-def]
    def _make(
        *,
        slug: str | None = None,
        name: str = "Acme Clinic",
        with_trial: bool = True,
    ) -> object:
        from app.modules.subscriptions import service as subscriptions_service

        slug = slug or f"t-{uuid.uuid4().hex[:8]}"
        tenant = tenancy_service.create_tenant(owner_db, name=name, slug=slug)
        # P2.2: capacity-consuming writes require a commercially usable
        # subscription. Opt out with with_trial=False for legacy fixtures.
        if with_trial and subscriptions_service.get_subscription(
            owner_db, tenant_id=tenant.id
        ) is None:
            subscriptions_service.create_trial_subscription(owner_db, tenant=tenant)
        owner_db.commit()
        return tenant

    return _make
