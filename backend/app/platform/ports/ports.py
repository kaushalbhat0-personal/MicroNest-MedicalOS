"""Ports: deployment-neutral interfaces. Business logic depends on these;
adapters (platform/adapters, infrastructure/) implement them. No business
logic branches on deployment — only adapter selection does.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class StoredObjectMeta:
    key: str
    size_bytes: int
    content_type: str
    sha256: str


class StoragePort(Protocol):
    def put(self, *, key: str, data: bytes, content_type: str) -> StoredObjectMeta: ...
    def get(self, *, key: str) -> bytes: ...
    def exists(self, *, key: str) -> bool: ...
    def delete(self, *, key: str) -> None: ...
    def signed_access(self, *, key: str, expires_seconds: int) -> str:
        """Opaque, expiring, unguessable access reference. Never a raw path."""
        ...


class NotifyChannel:
    EMAIL = "email"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    IN_APP = "in_app"


@dataclass(frozen=True)
class NotifyRequest:
    channel: str
    # References only — NEVER clinical payloads or PII content.
    to_ref: str
    template: str
    locale: str
    context_refs: dict[str, str]
    tenant_id: uuid.UUID | None = None


@dataclass(frozen=True)
class NotifyResult:
    provider_ref: str
    accepted: bool


class NotifyPort(Protocol):
    name: str

    def health(self) -> bool:
        """False unless a REAL provider is configured and reachable."""
        ...

    def send(self, request: NotifyRequest) -> NotifyResult: ...


@dataclass(frozen=True)
class ClockPort:
    """Override in tests for deterministic time."""

    def now(self) -> datetime:
        from app.platform.time import UTC

        return datetime.now(UTC)


# Payload keys that must NEVER cross a port boundary into notifications/storage
# metadata. Enforced by tests.
FORBIDDEN_PORT_KEYS = frozenset(
    {
        "password",
        "clinical_note",
        "diagnosis",
        "prescription",
        "image_bytes",
        "otp",
        "token",
        "secret",
    }
)


def assert_port_safe(payload: dict[str, object]) -> None:
    bad = {k for k in payload if isinstance(k, str) and k.lower() in FORBIDDEN_PORT_KEYS}
    if bad:
        raise ValueError(f"forbidden keys cross port boundary: {sorted(bad)}")
