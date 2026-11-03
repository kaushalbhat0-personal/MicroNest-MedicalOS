"""P4.8 security headers: every response path carries the hardening set.

Covers JSON API, health probes, RFC-7807 error envelopes, and the 404
oracle — the middleware runs outside the routers, so no path can dodge it.
"""

from __future__ import annotations

EXPECTED = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "frame-ancestors 'none'",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


def _assert_hardened(resp) -> None:  # type: ignore[no-untyped-def]
    for name, value in EXPECTED.items():
        assert resp.headers.get(name) == value, f"{name}: {resp.headers.get(name)}"
    assert (
        "Permissions-Policy" in resp.headers
        and "camera=()" in resp.headers["Permissions-Policy"]
    )
    # No version disclosure.
    assert "server" not in {k.lower() for k in resp.headers}
    # Correlation still works alongside the new headers.
    assert resp.headers.get("X-Request-ID")


def test_health_and_docs_carry_headers(client) -> None:  # type: ignore[no-untyped-def]
    _assert_hardened(client.get("/api/healthz"))
    _assert_hardened(client.get("/api/readyz"))
    _assert_hardened(client.get("/api/openapi.json"))


def test_api_success_and_error_paths_carry_headers(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from tests.helpers import login_client, provision_tenant, tenant_headers

    ctx = provision_tenant(owner_db, make_owner_user, make_tenant)
    doc = login_client(client, email=ctx["admin"].email)
    h = tenant_headers(ctx["tenant"].id)
    _assert_hardened(doc.get(f"/api/v1/tenants/{ctx['tenant'].id}", headers=h))
    # RFC-7807 envelopes: 401 (no auth), 404 (oracle), 422 (validation).
    _assert_hardened(client.get("/api/v1/auth/me"))
    missing = doc.get("/api/v1/tenants/00000000-0000-4000-8000-000000000000", headers=h)
    assert missing.status_code == 404
    _assert_hardened(missing)
    bad = client.post(
        "/api/v1/auth/login", json={"email": "not-an-email", "password": "x"}
    )
    assert bad.status_code == 422
    _assert_hardened(bad)


def test_hsts_absent_without_https_marker(client) -> None:  # type: ignore[no-untyped-def]
    # Test settings leave COOKIE_SECURE off: HSTS must not promise HTTPS
    # that the deployment does not provide.
    resp = client.get("/api/healthz")
    assert "Strict-Transport-Security" not in resp.headers


def test_hsts_gated_on_https_marker() -> None:  # type: ignore[no-untyped-def]
    from app.platform.security_headers import build_headers

    plain = build_headers(hsts=False)
    assert "Strict-Transport-Security" not in plain
    tls = build_headers(hsts=True)
    assert tls["Strict-Transport-Security"].startswith("max-age=31536000")
    # The gate in main.py wires hsts=settings.COOKIE_SECURE: plain HTTP
    # deployments never promise HSTS; only HTTPS-terminating ones do.
