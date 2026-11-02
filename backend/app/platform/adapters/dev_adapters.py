"""Development-only adapters. These exist so P1 can be exercised end-to-end
without production providers. They are FAIL-CLOSED:

- DevNotifyAdapter refuses to construct unless DEV_NOTIFICATIONS_ALLOW=true
  AND ENV != "prod" (also enforced by Settings validation).
- LocalStorageAdapter keeps bytes under a gitignored dir and serves them only
  through expiring HMAC-signed references — never raw paths, never public.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
import uuid

from app.platform import ids
from app.platform.config import Settings
from app.platform.ports.ports import (
    NotifyRequest,
    NotifyResult,
    StoredObjectMeta,
    assert_port_safe,
)


class DevNotifyAdapter:
    """Logs notification intents. NOT a production provider.

    `health()` always returns False so no release gate can mistake it for real.
    """

    name = "dev-console"

    def __init__(self, settings: Settings) -> None:
        if settings.ENV == "prod" or not settings.DEV_NOTIFICATIONS_ALLOW:
            raise RuntimeError(
                "DevNotifyAdapter is development-only and refuses to start here"
            )

    def health(self) -> bool:
        return False

    def send(self, request: NotifyRequest) -> NotifyResult:
        assert_port_safe(dict(request.context_refs))
        # Intentionally console-only; goes through scrubbed logging in the worker.
        print(f"[DEV-NOTIFY] channel={request.channel} to_ref={request.to_ref} "
              f"template={request.template}")
        return NotifyResult(provider_ref=f"dev-{ids.uuid7()}", accepted=True)


class LocalStorageAdapter:
    """Filesystem-backed StoragePort for dev/test. Same signed-access semantics."""

    def __init__(self, root: str, signing_secret: str) -> None:
        self._root = root
        self._secret = signing_secret.encode()
        os.makedirs(root, exist_ok=True)

    def _path(self, key: str) -> str:
        if ".." in key or key.startswith("/"):
            raise ValueError("invalid storage key")
        return os.path.join(self._root, key)

    def put(self, *, key: str, data: bytes, content_type: str) -> StoredObjectMeta:
        path = self._path(key)
        os.makedirs(os.path.dirname(path) or self._root, exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        digest = hashlib.sha256(data).hexdigest()
        return StoredObjectMeta(
            key=key, size_bytes=len(data), content_type=content_type, sha256=digest
        )

    def get(self, *, key: str) -> bytes:
        with open(self._path(key), "rb") as f:
            return f.read()

    def exists(self, *, key: str) -> bool:
        return os.path.exists(self._path(key))

    def delete(self, *, key: str) -> None:
        try:
            os.remove(self._path(key))
        except FileNotFoundError:
            pass

    def signed_access(self, *, key: str, expires_seconds: int) -> str:
        exp = int(time.time()) + expires_seconds
        nonce = uuid.uuid4().hex
        mac = hmac.new(
            self._secret, f"{key}:{exp}:{nonce}".encode(), hashlib.sha256
        ).hexdigest()
        return f"stor1.{nonce}.{exp}.{mac}"

    def verify_signed_access(self, *, key: str, token: str) -> bool:
        try:
            _, nonce, exp_s, mac = token.split(".")
            if int(exp_s) < int(time.time()):
                return False
            expected = hmac.new(
                self._secret, f"{key}:{exp_s}:{nonce}".encode(), hashlib.sha256
            ).hexdigest()
            return hmac.compare_digest(expected, mac)
        except (ValueError, TypeError):
            return False
