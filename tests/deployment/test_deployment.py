"""Deployment: fresh migrations apply cleanly, reverse cleanly, seeds exist,
no migrate-at-startup, compose config valid."""

import os

import pytest
from sqlalchemy import text


def test_migration_fresh_apply_and_rollback() -> None:
    import sqlalchemy

    url = os.environ.get(
        "TEST_OWNER_DATABASE_URL",
        "postgresql+psycopg2://hos_owner:owner-dev-pass@127.0.0.1:5432/healthcare_os_test",
    )
    engine = sqlalchemy.create_engine(url, isolation_level="AUTOCOMMIT")
    scratch = "healthcare_os_p1scratch"
    with engine.begin() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS " + scratch))
        conn.execute(text("CREATE DATABASE " + scratch))
    engine.dispose()
    scratch_url = url.rsplit("/", 1)[0] + "/" + scratch
    previous = os.environ.get("OWNER_DATABASE_URL")
    os.environ["OWNER_DATABASE_URL"] = scratch_url
    try:
        from alembic import command
        from alembic.config import Config

        cfg = Config("backend/alembic.ini")
        command.upgrade(cfg, "head")
        eng2 = sqlalchemy.create_engine(scratch_url)
        with eng2.begin() as conn:
            tables = conn.execute(
                text("SELECT count(*) FROM pg_tables WHERE schemaname='public'")
            ).scalar_one()
            assert tables and tables >= 15, tables
            seeds = conn.execute(
                text("SELECT count(*) FROM roles WHERE tenant_id IS NULL")
            ).scalar_one()
            assert seeds == 8, seeds
            rls = conn.execute(
                text(
                    "SELECT count(*) FROM pg_tables WHERE schemaname='public' AND rowsecurity"
                )
            ).scalar_one()
            assert rls and rls >= 6, rls
        eng2.dispose()
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")
    finally:
        if previous is None:
            del os.environ["OWNER_DATABASE_URL"]
        else:
            os.environ["OWNER_DATABASE_URL"] = previous
    engine = sqlalchemy.create_engine(url, isolation_level="AUTOCOMMIT")
    with engine.begin() as conn:
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :db AND pid <> pg_backend_pid()"
            ),
            {"db": scratch},
        )
        conn.execute(text("DROP DATABASE IF EXISTS " + scratch))
    engine.dispose()


def test_no_migrate_at_startup() -> None:
    import pathlib

    main_src = pathlib.Path("backend/app/main.py").read_text()
    assert "from alembic" not in main_src
    assert "alembic.command" not in main_src
    assert "upgrade(" not in main_src


def test_compose_config_valid() -> None:
    import shutil
    import subprocess

    if shutil.which("docker") is None:
        pytest.skip("docker not available")
    proc = subprocess.run(
        ["docker", "compose", "-f", "infrastructure/dev/docker-compose.yml", "config"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
