"""Platform configuration. Single source of truth for env-driven settings.

Secrets come from the environment (or a secret manager via adapter in later
phases). `.env` files are for local dev only and are NEVER committed.

Deployment profiles (P7). Profiles NEVER alter domain behavior — they only
describe which operational configuration is accepted at boot:

- development        : ENV=dev        (+ any DEPLOYMENT, default local)
- test               : ENV=test       (+ any DEPLOYMENT, default local)
- preview            : ENV=preview    + DEPLOYMENT=cloud (isolated resources)
- production-cloud   : ENV=production + DEPLOYMENT=cloud
- production-private : ENV=production + DEPLOYMENT=private
- production-onprem  : ENV=production + DEPLOYMENT=onprem

`validate_for_boot` fail-fasts on missing/invalid preview/production
settings. `create_app` and the worker call it at startup. Validation errors
name variables, never values — secret values are never printed.
"""

from __future__ import annotations

from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENVS = frozenset({"dev", "test", "preview", "prod", "production"})
DEPLOYMENTS = frozenset({"local", "cloud", "private", "onprem"})
STORAGE_ADAPTERS = frozenset({"local", "s3"})
NOTIFY_PROVIDERS = frozenset({"dev-console", "none"})


def _is_prod(env: str) -> bool:
    return env in ("prod", "production")


def _is_strict(env: str) -> bool:
    """Preview and production fail fast; dev/test stay lenient."""
    return env in ("prod", "production", "preview")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENV: str = Field(default="dev", description="dev | test | preview | prod | production")
    DEPLOYMENT: str = Field(default="local", description="local | cloud | private | onprem")
    OWNER_DATABASE_URL: str = Field(default="", description="Migrations/seeds only")
    APP_DATABASE_URL: str = Field(default="", description="Least-privilege app role URL")
    APP_ROLE_PASSWORD: str = Field(default="")
    JWT_SECRET: str = Field(default="")
    JWT_ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_MINUTES: int = Field(default=10)
    REFRESH_TOKEN_DAYS: int = Field(default=30)
    COOKIE_SECURE: bool = Field(default=False, description="True in prod (HTTPS)")
    COOKIE_DOMAIN: str | None = Field(default=None)
    # Explicit browser origins allowed to call the API with credentials.
    # No wildcards: credentials mode forbids them. Empty = same-origin only.
    ALLOWED_ORIGINS: list[str] = Field(default_factory=list)
    # Dev-only notification adapter. Prod/preview boot refuses it (fail-closed).
    DEV_NOTIFICATIONS_ALLOW: bool = Field(default=False)
    STORAGE_ADAPTER: str = Field(default="local", description="local | s3")
    STORAGE_LOCAL_ROOT: str = Field(default="./var/storage")
    # S3-compatible object storage (preview MinIO, cloud S3, private S3).
    S3_ENDPOINT_URL: str = Field(default="")
    S3_REGION: str = Field(default="us-east-1")
    S3_BUCKET: str = Field(default="")
    S3_ACCESS_KEY: str = Field(default="")
    S3_SECRET_KEY: str = Field(default="")
    S3_USE_TLS: bool = Field(default=True)
    # Preview convenience only: create the bucket if missing. Production uses
    # pre-created buckets owned by the platform team (default False).
    S3_ENSURE_BUCKET: bool = Field(default=False)
    # Notification provider selection. "none" = explicitly unavailable
    # (honest health); real providers (SES/SMS) land post-P7.
    NOTIFY_PROVIDER: str = Field(default="dev-console")
    # Require TLS to the database (cloud production). The driver enforces it
    # via ?sslmode=require in APP_DATABASE_URL.
    DB_SSL_REQUIRE: bool = Field(default=False)
    LOGIN_IP_LIMIT_PER_MIN: int = Field(default=10)
    LOGIN_ACCOUNT_LIMIT_PER_MIN: int = Field(default=5)
    # P4.8 hardening: token-guessing and spam surfaces. Defaults are
    # generous for single-process dev/test; tune per deployment.
    REFRESH_IP_LIMIT_PER_MIN: int = Field(default=30)
    RESET_CONFIRM_IP_LIMIT_PER_MIN: int = Field(default=10)
    INVITE_CREATE_USER_LIMIT_PER_MIN: int = Field(default=20)
    # O1.1 public signup/verification throttles (per deployment, like above).
    SIGNUP_IP_LIMIT_PER_MIN: int = Field(default=10)
    VERIFY_IP_LIMIT_PER_MIN: int = Field(default=10)
    VERIFY_RESEND_IP_LIMIT_PER_MIN: int = Field(default=10)
    VERIFY_RESEND_EMAIL_LIMIT_PER_HOUR: int = Field(default=3)
    API_HOST: str = Field(default="127.0.0.1")
    API_PORT: int = Field(default=8000)

    @field_validator("JWT_SECRET")
    @classmethod
    def _secret_length(cls, v: str) -> str:
        if len(v.encode()) < 32:
            raise ValueError("JWT_SECRET must be at least 32 bytes")
        return v

    @field_validator("DEV_NOTIFICATIONS_ALLOW")
    @classmethod
    def _dev_adapter_not_in_prod(cls, v: bool, info: object) -> bool:
        env = ""
        if hasattr(info, "data") and isinstance(info.data, dict):  # type: ignore[union-attr]
            env = str(info.data.get("ENV", ""))  # type: ignore[union-attr]
        if _is_strict(env) and v:
            raise ValueError("DEV_NOTIFICATIONS_ALLOW must be false outside dev/test")
        return v


def _db_name(url: str) -> str:
    try:
        return urlparse(url).path.lstrip("/").lower()
    except ValueError:
        return ""


def _localhost_only(origins: list[str]) -> bool:
    if not origins:
        return False
    for origin in origins:
        try:
            parts = urlparse(origin)
        except ValueError:
            return False
        if parts.scheme != "http" or parts.hostname not in (
            "localhost",
            "127.0.0.1",
        ):
            return False
    return True


def _origin_problems(origin: str, *, allow_http_localhost: bool) -> str | None:
    if origin == "*":
        return "wildcard origin is forbidden with credentials mode"
    try:
        parts = urlparse(origin)
    except ValueError:
        return "unparseable origin"
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return "origin must be a full http(s) URL with host"
    if parts.scheme == "http":
        if not (allow_http_localhost and parts.hostname in ("localhost", "127.0.0.1")):
            return "plain-http origin is only allowed for localhost in preview"
    return None


def validate_for_boot(settings: Settings) -> list[str]:
    """Return a list of boot-blocking configuration problems (empty = ok).

    Only variable NAMES are reported — never values.
    """
    problems: list[str] = []
    env, dep = settings.ENV, settings.DEPLOYMENT
    if env not in ENVS:
        problems.append(f"ENV must be one of {sorted(ENVS)}")
    if dep not in DEPLOYMENTS:
        problems.append(f"DEPLOYMENT must be one of {sorted(DEPLOYMENTS)}")
    if not _is_strict(env):
        return problems
    # Profile shape.
    if env == "preview" and dep != "cloud":
        problems.append("preview profile requires DEPLOYMENT=cloud")
    if _is_prod(env) and dep == "local":
        problems.append("production requires DEPLOYMENT=cloud|private|onprem")
    # Database.
    if not settings.APP_DATABASE_URL:
        problems.append("APP_DATABASE_URL is required in preview/production")
    else:
        dbname = _db_name(settings.APP_DATABASE_URL)
        if env == "preview" and "preview" not in dbname:
            problems.append(
                "preview must use an isolated preview database "
                "(APP_DATABASE_URL database name must contain 'preview')"
            )
        if _is_prod(env) and "preview" in dbname:
            problems.append("production must not point at a preview database (APP_DATABASE_URL)")
        if _is_prod(env) and dep == "cloud" and not settings.DB_SSL_REQUIRE:
            problems.append("DB_SSL_REQUIRE must be true for production-cloud")
    # Cookies / CORS.
    if not settings.COOKIE_SECURE:
        if _is_prod(env):
            problems.append("COOKIE_SECURE must be true in production (HTTPS)")
        elif not _localhost_only(settings.ALLOWED_ORIGINS):
            problems.append(
                "COOKIE_SECURE must be true in preview "
                "(exception: localhost-only origins for the local preview stack)"
            )
    domain = settings.COOKIE_DOMAIN or ""
    if settings.COOKIE_DOMAIN and ("://" in domain or ":" in domain):
        problems.append("COOKIE_DOMAIN must be a bare domain (no scheme or port)")
    if not settings.ALLOWED_ORIGINS:
        problems.append("ALLOWED_ORIGINS must list the web/portal origins explicitly")
    else:
        for origin in settings.ALLOWED_ORIGINS:
            problem = _origin_problems(origin, allow_http_localhost=(env == "preview"))
            if problem:
                problems.append(f"ALLOWED_ORIGINS entry is invalid: {problem}")
    # Adapters.
    if settings.STORAGE_ADAPTER not in STORAGE_ADAPTERS:
        problems.append(f"STORAGE_ADAPTER must be one of {sorted(STORAGE_ADAPTERS)}")
    elif settings.STORAGE_ADAPTER == "s3":
        for var in ("S3_ENDPOINT_URL", "S3_BUCKET", "S3_ACCESS_KEY", "S3_SECRET_KEY"):
            if not getattr(settings, var):
                problems.append(f"{var} is required when STORAGE_ADAPTER=s3")
        if _is_prod(env) and not settings.S3_USE_TLS:
            problems.append("S3_USE_TLS must be true in production")
    if settings.NOTIFY_PROVIDER not in NOTIFY_PROVIDERS:
        problems.append(f"NOTIFY_PROVIDER must be one of {sorted(NOTIFY_PROVIDERS)}")
    if settings.NOTIFY_PROVIDER == "dev-console":
        problems.append(
            "NOTIFY_PROVIDER=dev-console is development-only; "
            "use none (explicitly unavailable) in preview/production"
        )
    return problems


def require_valid_for_boot(settings: Settings) -> None:
    problems = validate_for_boot(settings)
    if problems:
        raise RuntimeError("invalid deployment configuration: " + "; ".join(problems))


def get_settings() -> Settings:
    return Settings()
