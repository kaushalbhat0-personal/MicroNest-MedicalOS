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
    "/api/v1/tenants/{tenant_id}/encounters",
    "/api/v1/tenants/{tenant_id}/encounters/{encounter_id}",
    "/api/v1/tenants/{tenant_id}/encounters/{encounter_id}/close",
    "/api/v1/tenants/{tenant_id}/encounters/{encounter_id}/clinical-notes",
    "/api/v1/tenants/{tenant_id}/encounters/{encounter_id}/observations",
    "/api/v1/tenants/{tenant_id}/encounters/{encounter_id}/diagnoses",
    "/api/v1/tenants/{tenant_id}/encounters/{encounter_id}/tooth-findings",
    "/api/v1/tenants/{tenant_id}/encounters/{encounter_id}/procedure-records",
    "/api/v1/tenants/{tenant_id}/encounters/{encounter_id}/prescriptions",
    "/api/v1/tenants/{tenant_id}/encounters/{encounter_id}/documents",
    "/api/v1/tenants/{tenant_id}/clinical-notes/{note_id}/finalize",
    "/api/v1/tenants/{tenant_id}/clinical-notes/{note_id}/amend",
    "/api/v1/tenants/{tenant_id}/observations/{observation_id}/amend",
    "/api/v1/tenants/{tenant_id}/observation-types",
    "/api/v1/tenants/{tenant_id}/diagnoses/{diagnosis_id}/resolve",
    "/api/v1/tenants/{tenant_id}/diagnoses/{diagnosis_id}/supersede",
    "/api/v1/tenants/{tenant_id}/diagnosis-codes",
    "/api/v1/tenants/{tenant_id}/medications",
    "/api/v1/tenants/{tenant_id}/prescriptions/{prescription_id}",
    "/api/v1/tenants/{tenant_id}/prescriptions/{prescription_id}/sign",
    "/api/v1/tenants/{tenant_id}/prescriptions/{prescription_id}/cancel",
    "/api/v1/tenants/{tenant_id}/prescriptions/{prescription_id}/correct",
    "/api/v1/tenants/{tenant_id}/dental-conditions",
    "/api/v1/tenants/{tenant_id}/dental-procedures",
    "/api/v1/tenants/{tenant_id}/tooth-findings/{finding_id}/resolve",
    "/api/v1/tenants/{tenant_id}/treatment-plans",
    "/api/v1/tenants/{tenant_id}/treatment-plans/{plan_id}",
    "/api/v1/tenants/{tenant_id}/treatment-plans/{plan_id}/items",
    "/api/v1/tenants/{tenant_id}/treatment-plans/{plan_id}/activate",
    "/api/v1/tenants/{tenant_id}/treatment-plans/{plan_id}/complete",
    "/api/v1/tenants/{tenant_id}/treatment-plans/{plan_id}/cancel",
    "/api/v1/tenants/{tenant_id}/plan-items/{item_id}/status",
    "/api/v1/tenants/{tenant_id}/procedure-records/{record_id}/status",
    "/api/v1/tenants/{tenant_id}/consents",
    "/api/v1/tenants/{tenant_id}/consents/{consent_id}/decide",
    "/api/v1/tenants/{tenant_id}/consents/{consent_id}/withdraw",
    "/api/v1/tenants/{tenant_id}/recalls",
    "/api/v1/tenants/{tenant_id}/recalls/{recall_id}/status",
    "/api/v1/tenants/{tenant_id}/service-catalog",
    "/api/v1/tenants/{tenant_id}/service-catalog/{item_id}",
    "/api/v1/tenants/{tenant_id}/service-catalog/{item_id}/activate",
    "/api/v1/tenants/{tenant_id}/service-catalog/{item_id}/deactivate",
    "/api/v1/tenants/{tenant_id}/estimates",
    "/api/v1/tenants/{tenant_id}/estimates/{estimate_id}",
    "/api/v1/tenants/{tenant_id}/estimates/{estimate_id}/lines",
    "/api/v1/tenants/{tenant_id}/estimates/{estimate_id}/issue",
    "/api/v1/tenants/{tenant_id}/estimates/{estimate_id}/cancel",
    "/api/v1/tenants/{tenant_id}/estimates/{estimate_id}/expire",
    "/api/v1/tenants/{tenant_id}/estimates/{estimate_id}/convert",
    "/api/v1/tenants/{tenant_id}/estimate-lines/{line_id}",
    "/api/v1/tenants/{tenant_id}/invoices",
    "/api/v1/tenants/{tenant_id}/invoices/{invoice_id}",
    "/api/v1/tenants/{tenant_id}/invoices/{invoice_id}/lines",
    "/api/v1/tenants/{tenant_id}/invoices/{invoice_id}/issue",
    "/api/v1/tenants/{tenant_id}/invoices/{invoice_id}/void",
    "/api/v1/tenants/{tenant_id}/invoice-lines/{line_id}",
    "/api/v1/tenants/{tenant_id}/invoices/{invoice_id}/balance",
    "/api/v1/tenants/{tenant_id}/patients/{patient_id}/credit-balance",
    "/api/v1/tenants/{tenant_id}/payments",
    "/api/v1/tenants/{tenant_id}/payments/{payment_id}",
    "/api/v1/tenants/{tenant_id}/payments/{payment_id}/allocations",
    "/api/v1/tenants/{tenant_id}/allocations/{allocation_id}/reverse",
    "/api/v1/tenants/{tenant_id}/refunds/{refund_id}",
    "/api/v1/tenants/{tenant_id}/payments/{payment_id}/refunds",
    "/api/v1/tenants/{tenant_id}/invoices/{invoice_id}/credit-notes",
    "/api/v1/tenants/{tenant_id}/credit-notes/{note_id}",
    "/api/v1/tenants/{tenant_id}/credit-notes/{note_id}/issue",
    "/api/v1/tenants/{tenant_id}/credit-notes/{note_id}/void",
    "/api/v1/tenants/{tenant_id}/payments/{payment_id}/receipt",
    "/api/v1/tenants/{tenant_id}/receipts/{receipt_id}",
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
