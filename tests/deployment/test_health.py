"""P7 health semantics: liveness is dependency-free, readiness is
200-ready / 503-degraded with coarse reason codes and no internals.
"""

from fastapi.testclient import TestClient

import app.main as main_module


def test_liveness_needs_no_database(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def _boom():  # type: ignore[no-untyped-def]
        raise AssertionError("liveness must not touch dependencies")

    monkeypatch.setattr(main_module, "get_factory", _boom)
    app = main_module.create_app()
    with TestClient(app) as client:
        resp = client.get("/api/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readiness_ready_when_db_reachable(client) -> None:
    resp = client.get("/api/readyz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready"}


def test_readiness_degraded_when_db_unreachable(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def _boom():  # type: ignore[no-untyped-def]
        raise RuntimeError("connection refused")

    monkeypatch.setattr(main_module, "get_factory", _boom)
    app = main_module.create_app()
    with TestClient(app) as test_client:
        resp = test_client.get("/api/readyz")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["reason"] == "db-unreachable"
    assert "refused" not in resp.text


def test_readiness_degraded_when_no_database_configured(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.platform.config import get_settings

    real = get_settings()
    object.__setattr__(real, "APP_DATABASE_URL", "")
    monkeypatch.setattr(main_module, "get_settings", lambda: real)
    app = main_module.create_app()
    with TestClient(app) as test_client:
        resp = test_client.get("/api/readyz")
    assert resp.status_code == 503
    assert resp.json()["reason"] == "db-not-configured"


def test_readiness_recovers_after_outage(client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls = {"n": 0}
    real_factory = main_module.get_factory

    def _flaky():  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("down")
        return real_factory()

    monkeypatch.setattr(main_module, "get_factory", _flaky)
    assert client.get("/api/readyz").status_code == 503
    recovered = client.get("/api/readyz")
    assert recovered.status_code == 200
    assert recovered.json() == {"status": "ready"}
