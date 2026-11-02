"""Application entrypoint. Thin by design: wiring only (middleware,
routers, error handlers, health). Domain logic lives in modules.

There is intentionally NO migration-on-startup. Migrations are explicit jobs
(alembic CLI / CI). Booting must never mutate the schema.
"""
from fastapi import APIRouter
from fastapi import FastAPI
from sqlalchemy import text

from app.api import errors as error_handlers
from app.api.deps import get_factory
from app.api.v1.router import router as v1_router
from app.platform.config import get_settings
from app.platform.logging_setup import configure_root_logging
from app.platform.request_context import RequestIDMiddleware

configure_root_logging()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Healthcare OS",
        version="0.1.0-p1",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(RequestIDMiddleware)
    error_handlers.register_handlers(app)

    health = APIRouter(tags=["health"])

    @health.get("/api/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @health.get("/api/readyz")
    def readyz() -> dict[str, str]:
        settings = get_settings()
        if not settings.APP_DATABASE_URL:
            return {"status": "degraded", "reason": "no database configured"}
        factory = get_factory()
        with factory() as session:
            session.execute(text("SELECT 1"))
        return {"status": "ready"}

    app.include_router(health)
    app.include_router(v1_router)
    return app


app = create_app()
