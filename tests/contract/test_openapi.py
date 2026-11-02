"""Contract: OpenAPI surface is stable and every protected route is gated."""


def _spec(client) -> dict:  # type: ignore[no-untyped-def]
    r = client.get("/api/openapi.json")
    assert r.status_code == 200, r.text
    return r.json()


REQUIRED_PATHS = [
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
    "/api/v1/auth/logout",
    "/api/v1/auth/me",
    "/api/v1/auth/sessions",
    "/api/v1/auth/password-reset/request",
    "/api/v1/auth/password-reset/confirm",
    "/api/v1/invites/accept",
    "/api/v1/platform/tenants",
    "/api/v1/platform/health",
    "/api/v1/tenants/mine",
    "/api/v1/tenants/{tenant_id}",
    "/api/v1/tenants/{tenant_id}/locations",
    "/api/v1/tenants/{tenant_id}/roles",
    "/api/v1/tenants/{tenant_id}/memberships",
    "/api/v1/tenants/{tenant_id}/invites",
    "/api/v1/tenants/{tenant_id}/practitioners",
    "/api/v1/tenants/{tenant_id}/verification",
    "/api/v1/tenants/{tenant_id}/audit",
    "/api/v1/tenants/{tenant_id}/patients",
    "/api/v1/tenants/{tenant_id}/patients/{patient_id}",
    "/api/v1/tenants/{tenant_id}/practitioners",
    "/api/v1/tenants/{tenant_id}/appointments",
    "/api/v1/tenants/{tenant_id}/appointments/{appointment_id}",
    "/api/v1/tenants/{tenant_id}/appointments/{appointment_id}/status",
    "/api/v1/tenants/{tenant_id}/appointments/{appointment_id}/cancel",
]


def test_required_paths_present(client) -> None:  # type: ignore[no-untyped-def]
    paths = _spec(client)["paths"]
    for p in REQUIRED_PATHS:
        assert p in paths, f"missing {p}"


def test_no_unexpected_write_routes_without_auth(client) -> None:  # type: ignore[no-untyped-def]
    spec = _spec(client)
    # Only explicitly public routes may lack a 401 response definition path;
    # every other operation must document 401/403 (gate proof in schema).
    public = {
        ("/api/v1/auth/login", "post"),
        ("/api/v1/auth/refresh", "post"),
        ("/api/v1/auth/password-reset/request", "post"),
        ("/api/v1/auth/password-reset/confirm", "post"),
        ("/api/v1/invites/accept", "post"),
        ("/api/healthz", "get"),
        ("/api/readyz", "get"),
    }
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            if method not in ("get", "post", "patch", "put", "delete"):
                continue
            if (path, method) in public:
                continue
            responses = {str(k) for k in op.get("responses", {})}
            assert (
                "401" in responses or "403" in responses
            ), f"{method} {path} missing auth responses"


def test_error_envelope_contract(client) -> None:  # type: ignore[no-untyped-def]
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401
    body = r.json()
    for key in ("type", "title", "status", "detail", "trace_id"):
        assert key in body, key
    assert r.headers.get("X-Request-ID"), "request id must propagate"
