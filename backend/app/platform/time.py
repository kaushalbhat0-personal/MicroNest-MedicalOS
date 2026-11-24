"""Time helpers. Single source for "now" (UTC) so tests can freeze time and
Python 3.10 stays supported (datetime.UTC is 3.11+).

API boundary contract: aware instants are normalized to UTC and serialized
with a trailing ``Z`` (not a host-local offset, and not ``+00:00``).
"""

from datetime import datetime, timezone

UTC = timezone.utc


def now() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """Return an aware UTC datetime. Naive values are treated as already-UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def to_api_utc(value: datetime) -> str:
    """Serialize an instant for JSON APIs: UTC with a trailing ``Z``."""
    return as_utc(value).isoformat().replace("+00:00", "Z")
