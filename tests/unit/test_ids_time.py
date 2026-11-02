"""IDs are time-ordered v7, unique; time helper is UTC."""
import uuid
from datetime import timezone

from app.platform import ids
from app.platform.time import UTC, now


def test_uuid7_version_and_monotonic() -> None:
    first = ids.uuid7()
    assert first.version == 7
    seen = {first}
    last = first
    for _ in range(200):
        nxt = ids.uuid7()
        assert nxt not in seen
        assert nxt.int >= last.int
        seen.add(nxt)
        last = nxt


def test_uuid7_parseable() -> None:
    assert uuid.UUID(str(ids.uuid7())).version == 7


def test_now_is_utc() -> None:
    assert now().tzinfo == timezone.utc
    assert UTC is timezone.utc
