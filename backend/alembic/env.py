"""Alembic environment. Explicit migration jobs only — the application
never calls this at startup (there is no hook from app.main).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine

from alembic import context
from app.modules.audit.models import AuditEvent  # noqa: F401
from app.modules.clinics.models import Location  # noqa: F401
from app.modules.identity.models import (  # noqa: F401
    AuthEvent,
    Credential,
    PasswordReset,
    Practitioner,
    Session,
    User,
)
from app.modules.tenancy.models import (  # noqa: F401
    Invitation,
    Membership,
    MembershipLocation,
    Role,
    Tenant,
    Verification,
)
from app.platform.db import Base
from app.platform.events.outbox import OutboxEvent  # noqa: F401

config = context.config


def get_url() -> str:
    url = os.environ.get("OWNER_DATABASE_URL") or config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError("OWNER_DATABASE_URL is not configured")
    return url


target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(get_url(), pool_pre_ping=True, future=True)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
