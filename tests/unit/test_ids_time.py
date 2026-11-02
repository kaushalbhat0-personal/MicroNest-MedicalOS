"""IDs are time-ordered v7, unique; time helper is UTC."""

import uuid
from datetime import timezone

from app.platform import ids
from app.platform.time import UTC, now


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
