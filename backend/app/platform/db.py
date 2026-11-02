"""Database engines, sessions, and RLS tenant-context helpers.

Two URLs by design:
- OWNER: migrations/seeds/RLS setup (bypasses RLS as table owner).
- APP:   least-privilege role used by the running API (RLS-enforced).

The app NEVER migrates at startup. Migrations are explicit jobs (alembic CLI / CI).
"""
import contextvars
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# Server-side request scope. Set per request inside a transaction; consumed by
# the RLS helper below. Never populated from client input without validation
# (see platform/authz/scope.py which resolves memberships first).
tenant_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "tenant_ctx", default=None
)
actor_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "actor_ctx", default=None
)


class Base(DeclarativeBase):
    pass


def make_session_factory(db_url: str) -> sessionmaker[Session]:
    engine = create_engine(db_url, pool_pre_ping=True, future=True)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


@contextmanager
def scoped_transaction(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Yield a session inside a transaction with RLS tenant context applied.

    SET LOCAL only lives for the transaction, so the context cannot leak
    across requests sharing pooled connections.
    """
    session = factory()
    try:
        session.begin()
        tenant = tenant_ctx.get()
        if tenant is not None:
            session.execute(
                text("SELECT set_config('app.tenant_id', :t, true)"),
                {"t": tenant},
            )
        actor = actor_ctx.get()
        if actor is not None:
            session.execute(
                text("SELECT set_config('app.actor_id', :a, true)"),
                {"a": actor},
            )
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
