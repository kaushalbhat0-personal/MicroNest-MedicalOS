"""Time helpers. Single source for "now" (UTC) so tests can freeze time and
Python 3.10 stays supported (datetime.UTC is 3.11+)."""

from datetime import datetime, timezone

UTC = timezone.utc


def now() -> datetime:
    return datetime.now(UTC)
