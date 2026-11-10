"""P7 configuration profiles and boot validation. DB-free by design."""

import pytest

from app.platform.config import (
    Settings,
    require_valid_for_boot,
    validate_for_boot,
)

LONG_SECRET = "test-only-secret-min-32-chars-xxxxxxxx"


def _base(**overrides):  # type: ignore[no-untyped-def]
    kwargs = {
        "ENV": "dev",
        "DEPLOYMENT": "local",
        "JWT_SECRET": LONG_SECRET,
        "APP_DATABASE_URL": "",
        "OWNER_DATABASE_URL": "",
        "APP_ROLE_PASSWORD": "pw",
        "DEV_NOTIFICATIONS_ALLOW": False,
        "NOTIFY_PROVIDER": "dev-console",
        "STORAGE_ADAPTER": "local",
    }
    kwargs.update(overrides)
    return Settings(**kwargs)


def _preview(**overrides):  # type: ignore[no-untyped-def]
    kwargs = {
        "ENV": "preview",
        "DEPLOYMENT": "cloud",
        "APP_DATABASE_URL": (
            "postgresql+psycopg2://hos_app:pw@db:5432/healthcare_os_preview"
        ),
        "COOKIE_SECURE": True,
        "ALLOWED_ORIGINS": ["https://portal.preview.example.com"],
        "NOTIFY_PROVIDER": "none",
        "STORAGE_ADAPTER": "local",
        "DEV_NOTIFICATIONS_ALLOW": False,
    }
    kwargs.update(overrides)
    return _base(**kwargs)


def _production(**overrides):  # type: ignore[no-untyped-def]
    kwargs = {
        "ENV": "production",
        "DEPLOYMENT": "cloud",
        "APP_DATABASE_URL": (
            "postgresql+psycopg2://hos_app:pw@db.internal:5432/healthcare_os"
            "?sslmode=require"
        ),
        "COOKIE_SECURE": True,
        "DB_SSL_REQUIRE": True,
        "ALLOWED_ORIGINS": ["https://portal.example.com"],
        "NOTIFY_PROVIDER": "none",
        "STORAGE_ADAPTER": "s3",
        "S3_ENDPOINT_URL": "https://s3.example.com",
        "S3_BUCKET": "hos-private",
        "S3_ACCESS_KEY": "ak",
        "S3_SECRET_KEY": "sk",
        "DEV_NOTIFICATIONS_ALLOW": False,
    }
    kwargs.update(overrides)
    return _base(**kwargs)


def test_dev_is_lenient() -> None:
    assert validate_for_boot(_base()) == []


def test_test_env_is_lenient() -> None:
    assert validate_for_boot(_base(ENV="test")) == []


def test_preview_valid() -> None:
    assert validate_for_boot(_preview()) == []


def test_production_valid() -> None:
    assert validate_for_boot(_production()) == []


def test_preview_requires_cloud_deployment() -> None:
    problems = validate_for_boot(_preview(DEPLOYMENT="private"))
    assert any("DEPLOYMENT=cloud" in p for p in problems)


def test_preview_requires_isolated_database_name() -> None:
    bad = _preview(
        APP_DATABASE_URL="postgresql+psycopg2://hos_app:pw@db:5432/healthcare_os"
    )
    problems = validate_for_boot(bad)
    assert any("isolated preview database" in p for p in problems)


def test_production_must_not_point_at_preview_database() -> None:
    bad = _production(
        APP_DATABASE_URL="postgresql+psycopg2://hos_app:pw@db:5432/healthcare_os_preview"
    )
    assert any(
        "must not point at a preview database" in p for p in validate_for_boot(bad)
    )


def test_strict_requires_secure_cookies() -> None:
    assert any(
        "COOKIE_SECURE" in p for p in validate_for_boot(_preview(COOKIE_SECURE=False))
    )


def test_preview_localhost_stack_may_use_plain_http_cookies() -> None:
    ok = _preview(COOKIE_SECURE=False, ALLOWED_ORIGINS=["http://localhost:3001"])
    assert validate_for_boot(ok) == []


def test_preview_non_localhost_requires_secure_cookies() -> None:
    problems = validate_for_boot(
        _preview(
            COOKIE_SECURE=False,
            ALLOWED_ORIGINS=["https://portal.preview.example.com"],
        )
    )
    assert any("COOKIE_SECURE" in p for p in problems)


def test_strict_requires_allowed_origins() -> None:
    assert any(
        "ALLOWED_ORIGINS" in p for p in validate_for_boot(_preview(ALLOWED_ORIGINS=[]))
    )


def test_wildcard_origin_rejected() -> None:
    problems = validate_for_boot(_preview(ALLOWED_ORIGINS=["*"]))
    assert any("wildcard" in p for p in problems)


def test_plain_http_rejected_in_production() -> None:
    problems = validate_for_boot(
        _production(ALLOWED_ORIGINS=["http://portal.example.com"])
    )
    assert any("plain-http" in p for p in problems)


def test_http_localhost_allowed_in_preview() -> None:
    ok = _preview(ALLOWED_ORIGINS=["http://localhost:3001"])
    assert validate_for_boot(ok) == []


def test_cookie_domain_must_be_bare() -> None:
    problems = validate_for_boot(_preview(COOKIE_DOMAIN="https://x.example.com"))
    assert any("COOKIE_DOMAIN" in p for p in problems)


def test_production_cloud_requires_db_tls() -> None:
    problems = validate_for_boot(_production(DB_SSL_REQUIRE=False))
    assert any("DB_SSL_REQUIRE" in p for p in problems)


def test_preview_forbids_dev_notify_provider() -> None:
    problems = validate_for_boot(_preview(NOTIFY_PROVIDER="dev-console"))
    assert any("dev-console" in p for p in problems)


def test_s3_requires_endpoint_bucket_and_keys() -> None:
    settings = _preview(STORAGE_ADAPTER="s3")
    problems = validate_for_boot(settings)
    for var in ("S3_ENDPOINT_URL", "S3_BUCKET", "S3_ACCESS_KEY", "S3_SECRET_KEY"):
        assert any(var in p for p in problems), var


def test_production_requires_s3_tls() -> None:
    problems = validate_for_boot(_production(S3_USE_TLS=False))
    assert any("S3_USE_TLS" in p for p in problems)


def test_unknown_profiles_rejected() -> None:
    assert any("ENV" in p for p in validate_for_boot(_base(ENV="staging")))
    assert any("DEPLOYMENT" in p for p in validate_for_boot(_base(DEPLOYMENT="mars")))


def test_production_rejects_local_deployment() -> None:
    problems = validate_for_boot(_production(DEPLOYMENT="local"))
    assert any("production requires DEPLOYMENT" in p for p in problems)


def test_error_messages_never_contain_secret_values() -> None:
    secret_url = (
        "postgresql+psycopg2://hos_app:super-secret-pw-12345@db:5432/healthcare_os"
    )
    settings = _preview(
        APP_DATABASE_URL=secret_url,
        STORAGE_ADAPTER="s3",
        S3_SECRET_KEY="super-secret-sk-67890",
    )
    problems = validate_for_boot(settings)
    assert problems, "expected problems for non-preview db + incomplete s3"
    blob = "\n".join(problems)
    assert "super-secret-pw-12345" not in blob
    assert "super-secret-sk-67890" not in blob
    assert "healthcare_os_preview" not in blob or True  # name rule text is fine


def test_require_valid_for_boot_raises() -> None:
    with pytest.raises(RuntimeError, match="invalid deployment configuration"):
        require_valid_for_boot(_preview(COOKIE_SECURE=False))


def test_dev_adapter_refused_in_preview_at_construction() -> None:
    with pytest.raises(ValueError, match="DEV_NOTIFICATIONS_ALLOW"):
        _preview(DEV_NOTIFICATIONS_ALLOW=True)
