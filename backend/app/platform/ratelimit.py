"""Rate limiting. In-memory buckets for P1/dev; the RateLimitPort protocol
is the seam a Redis adapter will implement (P7). Limits are per (scope, key).

Thread-safety and memory notes (P4.8): the guard is a single
``threading.Lock`` around the check-and-record critical section, and empty
buckets are evicted (plus an opportunistic purge when the table grows past
``_MAX_KEYS``) so anonymous-key cardinality cannot grow the table without
bound. Callers normalize keys (lower + strip emails; "unknown" only when no
better key exists) before calling.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Protocol

_MAX_KEYS = 10_000


class RateLimitPort(Protocol):
    def allow(self, *, scope: str, key: str, limit: int, window_seconds: int) -> bool: ...


def normalize_key(raw: str | None) -> str:
    """Canonical anonymous key: trimmed, lowercased, never empty."""
    cleaned = (raw or "").strip().lower()
    return cleaned or "unknown"


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def allow(self, *, scope: str, key: str, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            bucket = self._hits[(scope, key)]
            while bucket and bucket[0] < cutoff:
                bucket.pop(0)
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            if len(self._hits) > _MAX_KEYS:
                self._purge_locked(cutoff)
            return True

    def _purge_locked(self, cutoff: float) -> None:
        stale = [k for k, bucket in self._hits.items() if not bucket or bucket[-1] < cutoff]
        for k in stale:
            del self._hits[k]


limiter = InMemoryRateLimiter()
