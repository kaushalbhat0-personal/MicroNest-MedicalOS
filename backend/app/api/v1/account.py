"""Auth endpoints, part 2: logout, me, sessions, password reset."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.api.deps import get_current_user, get_db
from app.api.v1._shared import tenant_options
from app.modules.identity import schemas as S
from app.modules.identity import service as identity_service
from app.modules.identity.models import Session as SessionRow
from app.modules.identity.models import User
from app.modules.notifications import service as notify_service
from app.platform.ports.ports import NotifyRequest
from app.platform.security import cookies as cookie_util

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/logout", status_code=204, response_model=None)
def logout(
    response: Response,
    user_session: tuple[User, SessionRow] = Depends(get_current_user),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> None:
    from app.api.deps import get_cached_settings

    _, session = user_session
    identity_service.revoke_session(db, session, reason="logout")
    cookie_util.clear_auth_cookies(response, domain=get_cached_settings().COOKIE_DOMAIN)


@router.get("/me", response_model=S.MeResponse)
def me(
    user_session: tuple[User, SessionRow] = Depends(get_current_user),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.MeResponse:
    user, _ = user_session
    return S.MeResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_platform_admin=user.is_platform_admin,
        tenants=tenant_options(db, user),
    )


@router.get("/sessions", response_model=list[S.SessionInfo])
def list_sessions(
    user_session: tuple[User, SessionRow] = Depends(get_current_user),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> list[S.SessionInfo]:
    user, current = user_session
    rows = (
        db.execute(
            select(SessionRow)
            .where(SessionRow.user_id == user.id, SessionRow.revoked_at.is_(None))
            .order_by(SessionRow.created_at.desc())
        )
        .scalars()
        .all()
    )
    return [
        S.SessionInfo(
            id=r.id,
            created_at=r.created_at,
            last_used_at=r.last_used_at,
            expires_at=r.expires_at,
            ip=r.ip,
            current=(r.id == current.id),
        )
        for r in rows
    ]


@router.post("/sessions/revoke-all", status_code=204, response_model=None)
def revoke_all(
    user_session: tuple[User, SessionRow] = Depends(get_current_user),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> None:
    user, current = user_session
    # "Log out everywhere": revokes ALL sessions including the caller's.
    # The caller's access token remains valid until its short expiry.
    identity_service.revoke_all_user_sessions(db, user.id, reason="user_revoked")


@router.delete("/sessions/{session_id}", status_code=204, response_model=None)
def revoke_one(
    session_id: uuid.UUID,
    user_session: tuple[User, SessionRow] = Depends(get_current_user),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> None:
    from app.platform.errors import NotFoundError

    user, _ = user_session
    row = db.get(SessionRow, session_id)
    if row is None or row.user_id != user.id:
        # Own sessions only in P1. Cross-user revocation needs staff tooling (P5).
        raise NotFoundError("session not found")
    if row.revoked_at is not None:
        return
    identity_service.revoke_session(db, row, reason="user_revoked")


@router.post("/password-reset/request", status_code=202)
def reset_request(
    body: S.PasswordResetRequest,
    request: Request,
    db: DBSession = Depends(get_db),  # noqa: B008
) -> dict[str, str]:
    from app.api.deps import get_cached_settings
    from app.platform.ratelimit import limiter, normalize_key

    settings = get_cached_settings()
    ip = request.client.host if request.client else "unknown"
    throttled = not limiter.allow(
        scope="reset:ip",
        key=normalize_key(ip),
        limit=settings.LOGIN_IP_LIMIT_PER_MIN,
        window_seconds=60,
    )
    # No oracle: identical response whether or not the email exists.
    # Throttled callers get the same accepted response (no email is sent).
    user = identity_service.get_user_by_email(db, str(body.email))
    if user is not None and user.is_active and not throttled:
        identity_service.create_password_reset(db, user)
        notify_service.request_notification(
            db,
            NotifyRequest(
                channel="email",
                to_ref=str(user.id),
                template="password_reset",
                locale="en",
                context_refs={"user_id": str(user.id)},
                tenant_id=None,
            ),
        )
    return {"status": "accepted"}


@router.post("/password-reset/confirm")
def reset_confirm(
    body: S.PasswordResetConfirm,
    request: Request,
    db: DBSession = Depends(get_db),  # noqa: B008
) -> dict[str, str]:
    from app.api.deps import get_cached_settings
    from app.platform.errors import GoneError
    from app.platform.ratelimit import limiter, normalize_key

    settings = get_cached_settings()
    ip = request.client.host if request.client else "unknown"
    if not limiter.allow(
        scope="reset-confirm:ip",
        key=normalize_key(ip),
        limit=settings.RESET_CONFIRM_IP_LIMIT_PER_MIN,
        window_seconds=60,
    ):
        # No oracle: throttled guesses look exactly like bad tokens.
        raise GoneError("reset token invalid or expired")
    identity_service.consume_password_reset(db, token=body.token, new_password=body.new_password)
    return {"status": "ok"}
