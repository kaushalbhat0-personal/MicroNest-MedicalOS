"""IDs are time-ordered v7, unique; time helper is UTC."""

import uuid
from datetime import datetime, timedelta, timezone

from app.platform import ids
from app.platform.time import UTC, as_utc, now, to_api_utc


def test_uuid7_version_and_monotonic() -> None:
    import time

    first = ids.uuid7()
    assert first.version == 7
    seen = {first}
    for _ in range(200):
        nxt = ids.uuid7()
        assert nxt not in seen
        seen.add(nxt)
    # Time-ordered across millisecond boundaries.
    time.sleep(0.003)
    assert ids.uuid7().int > first.int


def test_uuid7_parseable() -> None:
    assert uuid.UUID(str(ids.uuid7())).version == 7


def test_now_is_utc() -> None:
    assert now().tzinfo == timezone.utc
    assert UTC is timezone.utc


def test_as_utc_normalizes_offsets() -> None:
    ist = timezone(timedelta(hours=5, minutes=30))
    local = datetime(2026, 11, 24, 15, 43, 11, 357518, tzinfo=ist)
    utc = as_utc(local)
    assert utc.tzinfo == UTC
    assert utc == datetime(2026, 11, 24, 10, 13, 11, 357518, tzinfo=UTC)
    naive = datetime(2026, 11, 24, 10, 13, 11, 357518)
    assert as_utc(naive) == datetime(2026, 11, 24, 10, 13, 11, 357518, tzinfo=UTC)


def test_to_api_utc_uses_z_not_host_offset() -> None:
    ist = timezone(timedelta(hours=5, minutes=30))
    local = datetime(2026, 11, 24, 15, 43, 11, 357518, tzinfo=ist)
    assert to_api_utc(local) == "2026-11-24T10:13:11.357518Z"
    assert to_api_utc(datetime(2026, 11, 24, 10, 13, 11, 357518, tzinfo=UTC)).endswith("Z")
    assert "+05:30" not in to_api_utc(local)
    assert "+00:00" not in to_api_utc(local)
