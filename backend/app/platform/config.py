"""Platform configuration. Single source of truth for env-driven settings.

Secrets come from the environment (or a secret manager via adapter in later
phases). `.env` files are for local dev only and are NEVER committed.
"""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENV: str = Field(default="dev", description="dev | test | prod")
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
    # Dev-only notification adapter. Prod boot refuses it (fail-closed).
    DEV_NOTIFICATIONS_ALLOW: bool = Field(default=False)
    STORAGE_LOCAL_ROOT: str = Field(default="./var/storage")
    LOGIN_IP_LIMIT_PER_MIN: int = Field(default=10)
    LOGIN_ACCOUNT_LIMIT_PER_MIN: int = Field(default=5)
    # P4.8 hardening: token-guessing and spam surfaces. Defaults are
    # generous for single-process dev/test; tune per deployment.
    REFRESH_IP_LIMIT_PER_MIN: int = Field(default=30)
    RESET_CONFIRM_IP_LIMIT_PER_MIN: int = Field(default=10)
    INVITE_CREATE_USER_LIMIT_PER_MIN: int = Field(default=20)
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
        if env == "prod" and v:
            raise ValueError("DEV_NOTIFICATIONS_ALLOW must be false in prod")
        return v


def get_settings() -> Settings:
    return Settings()
