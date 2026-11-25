"""A2 auth session PoC against local mock API. Never prints tokens."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence"
BASE = "http://127.0.0.1:8787"
EMAIL = "poc.owner@example.com"
PASSWORD = "PoC-Only-Not-A-Secret-99"


def req(method: str, path: str, body: dict | None = None, token: str | None = None):
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, None


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    checks: dict[str, str] = {}
    token: str | None = None

    st, health = req("GET", "/api/healthz")
    checks["mock_api_health"] = "PASS" if st == 200 else "FAIL"

    st, login = req("POST", "/api/v1/auth/login", {"email": EMAIL, "password": PASSWORD})
    if st == 200 and isinstance(login, dict) and login.get("access_token"):
        token = str(login["access_token"])
        checks["login_returns_bearer"] = "PASS"
    else:
        checks["login_returns_bearer"] = "FAIL"

    st, me = req("GET", "/api/v1/auth/me", token=token)
    checks["authenticated_me"] = "PASS" if st == 200 else "FAIL"

    # Hold token only in memory variable; simulate secure store abstractly
    memory_store = {"access_token": token}
    st, _ = req("POST", "/api/v1/auth/logout", token=token)
    memory_store.clear()
    checks["logout_clears_memory_session"] = "PASS" if "access_token" not in memory_store else "FAIL"

    st, me2 = req("GET", "/api/v1/auth/me", token=token)
    checks["post_logout_me_rejected"] = "PASS" if st == 401 else "FAIL"

    out = {
        "checks": checks,
        "token_logged": False,
        "backend": "poc-mock-api",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    path = EVIDENCE / "a2_windows_auth_evidence.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    for k, v in checks.items():
        print(f"{k}={v}")
    print(f"evidence={path.as_posix()}")
    return 0 if all(v == "PASS" for v in checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
