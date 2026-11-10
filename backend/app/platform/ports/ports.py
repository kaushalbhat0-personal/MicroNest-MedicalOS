"""Ports: deployment-neutral interfaces. Business logic depends on these;
adapters (platform/adapters, infrastructure/) implement them. No business
logic branches on deployment — only adapter selection does.
"""

from __future__ import annotations

import re
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
# metadata. Enforced by tests. This is a blacklist backstop: notification
# envelopes additionally pass the allow-list in
# assert_notification_refs_safe (refs must be *_id shaped).
FORBIDDEN_PORT_KEYS = frozenset(
    {
        "password",
        "clinical_note",
        "clinical_notes",
        "subjective",
        "objective",
        "assessment",
        "plan_notes",
        "diagnosis",
        "diagnoses",
        "prescription",
        "medication",
        "image",
        "image_bytes",
        "otp",
        "token",
        "secret",
        "credentials",
        "email",
        "phone",
        "ssn",
        "dob",
        "date_of_birth",
        "address",
    }
)


def _forbidden_keys_deep(payload: object) -> set[str]:
    """Collect forbidden keys at every nesting level (dicts inside dicts,
    lists, tuples, sets). Only keys are inspected — values are opaque ids."""
    found: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(key, str) and key.lower() in FORBIDDEN_PORT_KEYS:
                found.add(key)
            found |= _forbidden_keys_deep(value)
    elif isinstance(payload, list | tuple | set | frozenset):
        for item in payload:
            found |= _forbidden_keys_deep(item)
    return found


def assert_port_safe(payload: dict[str, object]) -> None:
    bad = _forbidden_keys_deep(payload)
    if bad:
        raise ValueError(f"forbidden keys cross port boundary: {sorted(bad)}")


# Notification context_refs allow-list (shape, not vocabulary): reference
# fields only. Existing producers use invitation_id / user_id /
# appointment_id; future recall reminders would use recall_id, etc. Values
# must be scalar ids — contact strings (emails/phones) are rejected, and the
# delivery destination itself travels via to_ref (server-resolved), never in
# context_refs.
_REF_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}_id$")


def assert_notification_refs_safe(refs: dict[str, object]) -> None:
    """Allow-list for notification context_refs: every key must be a
    snake_case *_id reference; every value a scalar id (str/int/UUID)."""
    import uuid as _uuid

    for key, value in refs.items():
        if not isinstance(key, str) or _REF_KEY_RE.match(key) is None:
            raise ValueError(f"notification refs allow only *_id keys, got: {key!r}")
        if isinstance(value, _uuid.UUID):
            continue
        if isinstance(value, bool):
            raise ValueError(f"notification ref {key!r} must be an id, not a boolean")
        if isinstance(value, int):
            continue
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"notification ref {key!r} must be a non-empty id")
        lowered = value.strip().lower()
        if "@" in lowered or "+" in lowered and any(c.isdigit() for c in lowered):
            raise ValueError(f"notification ref {key!r} must be an id reference, not a contact")
