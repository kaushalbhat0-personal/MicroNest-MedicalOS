"""CORS: explicit origins only, credentials-safe, never wildcard."""

from fastapi.testclient import TestClient


def _app_with_origins(monkeypatch, origins):  # type: ignore[no-untyped-def]
    import json

    from app import main as main_module

    monkeypatch.setenv("ALLOWED_ORIGINS", json.dumps(origins))
    return main_module.create_app()


def test_preflight_allowed_origin(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    app = _app_with_origins(monkeypatch, ["http://localhost:3000"])
    c = TestClient(app, base_url="http://test")
    r = c.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.status_code == 200, r.text
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_disallowed_origin_gets_no_cors_headers(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    app = _app_with_origins(monkeypatch, ["http://localhost:3000"])
    c = TestClient(app, base_url="http://test")
    r = c.get("/api/healthz", headers={"Origin": "http://evil.example"})
    assert r.status_code == 200
    assert "access-control-allow-origin" not in r.headers


def test_no_origins_configured_means_same_origin_only(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    app = _app_with_origins(monkeypatch, [])
    c = TestClient(app, base_url="http://test")
    r = c.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in r.headers
