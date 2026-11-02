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
    "credentials",
    "dental_procedure_records",
    "document_references",
    "encounter_diagnoses",
    "encounters",
    "invitations",
    "locations",
    "membership_locations",
    "memberships",
    "observations",
    "outbox_events",
    "password_resets",
    "practitioner_verifications",
    "practitioners",
    "prescription_items",
    "prescriptions",
    "recalls",
    "roles",
    "sessions",
    "tenants",
    "tooth_finding_surfaces",
    "tooth_findings",
    "treatment_plan_items",
    "treatment_plans",
    "users",
    "patients",
    "appointments",
]
# Global read-only catalogs (observation_types, diagnosis_codes, medications,
# dental_conditions, dental_procedures) are seeded by migrations and never
# truncated: no write endpoint exists, so tests cannot dirty them.


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
        for name, perms in SEED_ROLES.items():
            import json

            session.execute(
                text(
                    "INSERT INTO roles (id, tenant_id, name, permissions, is_seed, created_at) "
                    "VALUES (gen_random_uuid(), NULL, :name, :perms, true, :now)"
                ),
                {"name": name, "perms": json.dumps(sorted(perms)), "now": now},
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
    def _make(*, slug: str | None = None, name: str = "Acme Clinic") -> object:
        slug = slug or f"t-{uuid.uuid4().hex[:8]}"
        tenant = tenancy_service.create_tenant(owner_db, name=name, slug=slug)
        owner_db.commit()
        return tenant

    return _make
