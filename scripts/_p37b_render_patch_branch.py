"""Patch Render service branch + disable auto-deploy only. No secrets printed."""
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


def api(method: str, path: str, key: str, body: object | None = None) -> tuple[int, object]:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"https://api.render.com/v1{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "healthcare-os-p37b",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:  # noqa: S310
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        err = exc.read().decode(errors="replace")[:500].replace(key, "[REDACTED]")
        return exc.code, {"error": err}


def main() -> int:
    key = load_env().get("RENDER_API_KEY", "")
    if not key:
        print("MISSING_KEY")
        return 2

    for body in (
        {"autoDeploy": "no", "branch": "release/p3-7b-staging"},
        {"autoDeploy": False, "branch": "release/p3-7b-staging"},
        {"branch": "release/p3-7b-staging"},
    ):
        code, payload = api("PATCH", f"/services/{SERVICE_ID}", key, body)
        print(f"PATCH body_keys={list(body)} -> HTTP {code}")
        if code in (200, 201):
            svc = payload.get("service", payload) if isinstance(payload, dict) else {}
            if isinstance(svc, dict):
                print(
                    f"AFTER branch={svc.get('branch')!r} autoDeploy={svc.get('autoDeploy')}"
                )
            break
        else:
            err = payload.get("error") if isinstance(payload, dict) else payload
            print(f"error_snip={str(err)[:200]}")

    code, payload = api("GET", f"/services/{SERVICE_ID}", key)
    print(f"GET service HTTP {code}")
    if isinstance(payload, dict):
        svc = payload.get("service", payload)
        if isinstance(svc, dict):
            details = svc.get("serviceDetails") if isinstance(svc.get("serviceDetails"), dict) else {}
            print(
                f"VERIFY name={svc.get('name')!r} branch={svc.get('branch')!r} "
                f"autoDeploy={svc.get('autoDeploy')} url={details.get('url')!r}"
            )

    # Probe env-var endpoints
    for path in (
        f"/services/{SERVICE_ID}/env-vars",
        f"/services/{SERVICE_ID}/envvars",
        f"/services/{SERVICE_ID}/environment",
    ):
        code, _ = api("GET", path, key)
        print(f"GET {path} -> HTTP {code}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
