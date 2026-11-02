"""Rate limiting. In-memory buckets for P1/dev; the RateLimitPort protocol
is the seam a Redis adapter will implement (P7). Limits are per (scope, key).
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Protocol


class RateLimitPort(Protocol):
    def allow(self, *, scope: str, key: str, limit: int, window_seconds: int) -> bool: ...


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], list[float]] = defaultdict(list)

    def allow(self, *, scope: str, key: str, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        bucket = self._hits[(scope, key)]
        cutoff = now - window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.pop(0)
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True


limiter = InMemoryRateLimiter()
