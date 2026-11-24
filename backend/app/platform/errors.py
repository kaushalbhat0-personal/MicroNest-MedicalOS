"""Shared domain errors. Services raise these; the API layer maps them to
RFC-7807 responses. No stack traces or internals leak to clients.
"""


class DomainError(Exception):
    code = "domain_error"
    status = 400


class AuthError(DomainError):
    code = "authentication_failed"
    status = 401


class SessionReuseError(AuthError):
    code = "session_reuse_detected"


class ForbiddenError(DomainError):
    code = "forbidden"
    status = 403


class NotFoundError(DomainError):
    code = "not_found"
    status = 404


class ConflictError(DomainError):
    code = "conflict"
    status = 409


class EntitlementExceededError(ConflictError):
    """Plan capacity or commercial write eligibility denied.

    Subclasses ConflictError (409) so existing clients treating capacity races
    as conflicts keep working. ``code`` distinguishes entitlement denials.
    """

    code = "entitlement_exceeded"

    def __init__(
        self,
        message: str,
        *,
        entitlement_key: str | None = None,
        reason_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.entitlement_key = entitlement_key
        self.reason_code = reason_code


class RateLimitError(DomainError):
    code = "rate_limited"
    status = 429


class ValidationError(DomainError):
    code = "validation_failed"
    status = 422


class GoneError(DomainError):
    code = "gone"
    status = 410


class ServiceUnavailableError(DomainError):
    code = "service_unavailable"
    status = 503
