"""P4.8 rate-limit hardening: window, isolation, concurrency, abuse surfaces.

Unit tests pin the limiter contract (sliding window, per-key isolation,
thread safety, bounded memory). API tests pin the abuse surfaces with
oracle-preserving responses: throttled callers see exactly what a normal
failure looks like.
"""

from __future__ import annotations

import threading

from app.platform.ratelimit import InMemoryRateLimiter, normalize_key


def test_normalize_key() -> None:
    assert normalize_key("  Alice@Example.COM ") == "alice@example.com"
    assert normalize_key(None) == "unknown"
    assert normalize_key("   ") == "unknown"


def test_window_expiry_and_key_isolation() -> None:
    import time

    limiter = InMemoryRateLimiter()
    assert limiter.allow(scope="s", key="a", limit=2, window_seconds=60)
    assert limiter.allow(scope="s", key="a", limit=2, window_seconds=60)
    assert not limiter.allow(scope="s", key="a", limit=2, window_seconds=60)
    # Same limit, different key/scope unaffected.
    assert limiter.allow(scope="s", key="b", limit=2, window_seconds=60)
    assert limiter.allow(scope="other", key="a", limit=2, window_seconds=60)
    # Tiny window expires.
    fast = InMemoryRateLimiter()
    assert fast.allow(scope="s", key="a", limit=1, window_seconds=1)
    assert not fast.allow(scope="s", key="a", limit=1, window_seconds=1)
    time.sleep(1.05)
    assert fast.allow(scope="s", key="a", limit=1, window_seconds=1)


def test_limiter_bounded_and_thread_safe() -> None:
    limiter = InMemoryRateLimiter()
    gate = threading.Barrier(6)
    allowed: list[bool] = []

    def hammer(key: str) -> None:
        gate.wait(timeout=30)
        for _ in range(20):
            allowed.append(
                limiter.allow(scope="race", key=key, limit=10, window_seconds=60)
            )

    threads = [threading.Thread(target=hammer, args=(f"k{i % 2}",)) for i in range(5)]
    for t in threads:
        t.start()
    gate.wait(timeout=30)
    for t in threads:
        t.join(timeout=120)
    # Exactly `limit` True per key despite concurrent writers.
    assert sum(1 for ok in allowed if ok) == 20
    assert len(allowed) == 100
    # Stale anonymous keys cannot grow the table without bound.
    for i in range(200):
        limiter.allow(scope="anon", key=f"10.0.0.{i}", limit=100, window_seconds=60)
    assert len(limiter._hits) <= 10_000


def test_login_account_throttle_is_oracle_safe(
    client, owner_db, make_owner_user
) -> None:  # type: ignore[no-untyped-def]
    make_owner_user(email="throttle@example.com")
    bad = {"email": "throttle@example.com", "password": "wrong-password-xyz"}
    first = client.post("/api/v1/auth/login", json=bad)
    assert first.status_code == 401
    assert first.json()["detail"] == "authentication failed"
    for _ in range(4):
        r = client.post("/api/v1/auth/login", json=bad)
        assert r.status_code == 401
        assert r.json()["detail"] == "authentication failed"
    # Bucket spent: the 6th attempt is throttled (same 401 envelope).
    throttled_bad = client.post("/api/v1/auth/login", json=bad)
    assert throttled_bad.status_code == 401
    assert throttled_bad.json()["detail"] == "too many attempts"
    # Correct password earns nothing more once throttled: identical body.
    good = client.post(
        "/api/v1/auth/login",
        json={"email": "throttle@example.com", "password": "password-12345-abc"},
    )
    assert good.status_code == 401
    assert good.json() == throttled_bad.json() | {"trace_id": good.json()["trace_id"]}


def test_refresh_ip_throttle_stays_401(client) -> None:  # type: ignore[no-untyped-def]
    from fastapi.testclient import TestClient as TC

    probe = TC(client.app, base_url="http://test")
    bodies = [
        probe.post(
            "/api/v1/auth/refresh", headers={"Cookie": "hos_refresh=bogus.secret"}
        ).json()
        for _ in range(31)
    ]
    assert all(b["status"] == 401 for b in bodies)
    assert bodies[-1]["detail"] == "too many attempts"


def test_reset_confirm_throttle_matches_bad_token(
    client,
) -> None:  # type: ignore[no-untyped-def]
    bad = {"token": "bogus", "new_password": "brand-new-password-1"}
    first = client.post("/api/v1/auth/password-reset/confirm", json=bad)
    assert first.status_code == 410
    for _ in range(10):
        r = client.post("/api/v1/auth/password-reset/confirm", json=bad)
        assert r.status_code == 410
        assert r.json()["type"] == first.json()["type"]


def test_invite_create_throttle_is_429(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from tests.helpers import login_client, provision_tenant, tenant_headers

    ctx = provision_tenant(owner_db, make_owner_user, make_tenant)
    boss = login_client(client, email=ctx["admin"].email)
    tid = str(ctx["tenant"].id)
    h = tenant_headers(tid)
    last = None
    for i in range(21):
        last = boss.post(
            f"/api/v1/tenants/{tid}/invites",
            headers=h,
            json={"email": f"spam{i}@example.com", "role": "staff"},
        )
        assert last.status_code in (200, 429), last.text
    assert last is not None and last.status_code == 429
    body = last.json()
    for key in ("type", "title", "status", "detail", "trace_id"):
        assert key in body, key
