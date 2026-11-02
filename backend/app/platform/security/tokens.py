"""Tokens: short-lived JWT access tokens + opaque rotating refresh tokens.

Refresh tokens are stored ONLY as SHA-256 hashes. Reuse of a rotated token
revokes the whole session family (theft detection).
"""
import hashlib
import secrets
import uuid
from datetime import datetime

import jwt

from app.platform import ids
from app.platform.time import UTC

ACCESS_TYP = "access"


def new_refresh_secret() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def new_session_family() -> uuid.UUID:
    return ids.uuid7()


def create_access_token(
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    secret: str,
    algorithm: str = "HS256",
    minutes: int = 10,
) -> str:
    now = datetime.now(UTC)
    payload = {
        "typ": ACCESS_TYP,
        "sub": str(user_id),
        "sid": str(session_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
        "jti": str(ids.uuid7()),
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_access_token(token: str, *, secret: str, algorithms: list[str]) -> dict[str, object]:
    data = jwt.decode(token, secret, algorithms=algorithms)
    if not isinstance(data, dict) or data.get("typ") != ACCESS_TYP:
        raise jwt.InvalidTokenError("not an access token")
    return data
