"""Auth cookies. Browser auth uses HttpOnly cookies; Bearer header is accepted
as a fallback for future native clients (same verification, same scope)."""

from fastapi import Response

ACCESS_COOKIE = "hos_access"
REFRESH_COOKIE = "hos_refresh"


def set_auth_cookies(
    response: Response,
    *,
    access: str,
    refresh: str,
    secure: bool,
    domain: str | None,
    refresh_days: int,
) -> None:
    response.set_cookie(
        ACCESS_COOKIE,
        access,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/api",
        domain=domain,
        max_age=10 * 60,
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/api/v1/auth",
        domain=domain,
        max_age=refresh_days * 24 * 3600,
    )


def clear_auth_cookies(response: Response, *, domain: str | None) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/api", domain=domain)
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth", domain=domain)
