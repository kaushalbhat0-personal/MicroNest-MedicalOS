"""Security response headers. Single authority for HTTP hardening headers.

Applied as a pure-Starlette middleware so every response path is covered:
JSON API, health/readiness probes, and RFC-7807 error envelopes (which are
plain JSONResponses). Rationale per header:

- ``X-Content-Type-Options: nosniff`` — API serves JSON only; blocks MIME
  sniffing that could turn an upload/metadata reflection into script.
- ``X-Frame-Options: DENY`` + ``Content-Security-Policy: frame-ancestors
  'none'`` — the API has no embeddable UI (even /api/docs is a developer
  tool, not part of the product surface); deny framing to kill clickjacking.
  A full CSP (``default-src``/``script-src``) is deliberately NOT set: it
  would break the Swagger UI served at /api/docs, which legitimately needs
  inline scripts. Revisit if docs are ever served from the API in prod.
- ``Referrer-Policy: no-referrer`` — authenticated API traffic must never
  leak tenant IDs or tokens via Referer headers.
- ``Permissions-Policy`` — the API needs no browser device features; turn
  the sensitive ones off by default.
- ``Cache-Control: no-store`` — all API responses are authenticated and
  tenant-scoped; forbid shared/proxy caches from storing them.
- ``Strict-Transport-Security`` — sent only when ``COOKIE_SECURE`` is true,
  i.e. the deployment terminates HTTPS in front of the app (the only setup
  where HSTS is both true and safe). Never sent over plain HTTP: browsers
  ignore it there, and sending it would be a false promise.
- ``Server`` header is stripped — version disclosure with zero utility.

No secrets, no PHI, no per-request state: safe for every response.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


def build_headers(*, hsts: bool) -> dict[str, str]:
    """Header set for one deployment mode. Pure function for testability."""
    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Content-Security-Policy": "frame-ancestors 'none'",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": (
            "camera=(), microphone=(), geolocation=(), payment=(), usb=(), "
            "magnetometer=(), gyroscope=(), accelerometer=()"
        ),
        "Cache-Control": "no-store",
    }
    if hsts:
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return headers


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach the static hardening headers to every response."""

    def __init__(self, app: object, *, hsts: bool = False) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._headers = build_headers(hsts=hsts)

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        response: Response = await call_next(request)
        for name, value in self._headers.items():
            response.headers[name] = value
        if "server" in response.headers:
            del response.headers["server"]
        return response
