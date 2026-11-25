"""Probe Render API scopes without printing secrets."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE_ID = "srv-dc2tmb49v7es73dkqc9g"


def load_env() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def api(method: str, path: str, key: str, body: object | None = None) -> tuple[int, str]:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"https://api.render.com/v1{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "healthcare-os-p37b-deploy",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
            raw = resp.read().decode()
            return resp.status, raw[:300]
    except urllib.error.HTTPError as exc:
        err = exc.read().decode(errors="replace")[:400].replace(key, "[REDACTED]")
        return exc.code, err


def main() -> None:
    env = load_env()
    key = env.get("RENDER_API_KEY", "")
    print(f"RENDER_API_KEY={'PRESENT' if key else 'MISSING'}")
    if not key:
        return
    for method, path, body in (
        ("GET", f"/services/{SERVICE_ID}", None),
        ("GET", f"/services/{SERVICE_ID}/env-vars", None),
        ("PATCH", f"/services/{SERVICE_ID}", {"autoDeploy": "no"}),
    ):
        code, snip = api(method, path, key, body)
        # scrub any accidental key material
        snip = snip.replace(key, "[REDACTED]")
        print(f"{method} {path} -> HTTP {code}")
        if code >= 400:
            print(f"  body={snip}")


if __name__ == "__main__":
    main()
