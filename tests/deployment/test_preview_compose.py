"""P7 preview stack guards: isolated resources, never production."""

import pathlib
import shutil
import subprocess

import pytest

PREVIEW_COMPOSE = "infrastructure/preview/docker-compose.yml"


def _compose_config() -> str:
    if shutil.which("docker") is None:
        pytest.skip("docker not available")
    import os

    # Dummy format-valid placeholders (never real secrets): compose config
    # only interpolates; boot validation happens inside containers.
    env = {
        **os.environ,
        "PREVIEW_OWNER_PASSWORD": "ci-preview-owner-pw",
        "PREVIEW_APP_PASSWORD": "ci-preview-app-pw",
        "PREVIEW_JWT_SECRET": "ci-only-secret-min-32-chars-xxxxxxxx",
        "PREVIEW_MINIO_ROOT_USER": "ci-minio-admin",
        "PREVIEW_MINIO_ROOT_PASSWORD": "ci-minio-pw-12345",
    }
    proc = subprocess.run(
        ["docker", "compose", "-f", PREVIEW_COMPOSE, "config"],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    return proc.stdout


def test_preview_compose_file_exists() -> None:
    assert pathlib.Path(PREVIEW_COMPOSE).exists()
    assert pathlib.Path("apps/web/Dockerfile").exists()
    assert pathlib.Path("infrastructure/preview/preview.env.example").exists()


def test_preview_compose_config_valid() -> None:
    _compose_config()


def test_preview_uses_isolated_database() -> None:
    config = _compose_config()
    assert "healthcare_os_preview" in config
    # The production database name must never appear as a database here.
    # ("healthcare_os_preview" contains the prefix; match the exact value.)
    assert "POSTGRES_DB: healthcare_os\n" not in config
    assert "healthcare_os_test" not in config


def test_preview_has_all_required_services() -> None:
    config = _compose_config()
    for service in ("db:", "storage:", "api:", "worker:", "web:"):
        assert service in config, f"missing service {service}"


def test_preview_env_example_is_placeholder_only() -> None:
    example = pathlib.Path("infrastructure/preview/preview.env.example").read_text()
    assert "change-me" in example, "preview example must use placeholder secrets"
    assert "healthcare_os_preview" in example
    assert "preview" in example.lower()
