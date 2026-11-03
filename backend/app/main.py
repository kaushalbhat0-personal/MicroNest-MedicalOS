"""Application entrypoint. Thin by design: wiring only (middleware,
routers, error handlers, health). Domain logic lives in modules.

There is intentionally NO migration-on-startup. Migrations are explicit jobs
(alembic CLI / CI). Booting must never mutate the schema.
"""

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import errors as error_handlers
from app.api.deps import get_factory
from app.api.v1.router import router as v1_router
from app.platform.config import get_settings
from app.platform.logging_setup import configure_root_logging
from app.platform.request_context import RequestIDMiddleware
from app.platform.security_headers import SecurityHeadersMiddleware

configure_root_logging()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Healthcare OS",
        version="0.1.0-p1",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(RequestIDMiddleware)
    # HSTS only when the deployment terminates HTTPS (COOKIE_SECURE is the
    # prod-HTTPS marker); the remaining headers are safe on every response.
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.COOKIE_SECURE)
    # Browsers: the web app runs on a different origin in dev/prod.
    # Credentials mode => explicit origins only, never "*".
    if settings.ALLOWED_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.ALLOWED_ORIGINS,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization", "X-Tenant", "X-Request-ID"],
            max_age=600,
        )
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
