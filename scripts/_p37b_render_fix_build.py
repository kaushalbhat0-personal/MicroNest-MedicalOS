"""Inspect failed deploy + set build/start commands. No secrets printed."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE_ID = "srv-dc2tmb49v7es73dkqc9g"
DEPLOY_ID = "dep-dc2u8du1egvs73frq6o0"


def load_env() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def api(method: str, path: str, key: str, body: object | None = None) -> object:
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
        with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
            raw = resp.read().decode()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        err = exc.read().decode(errors="replace")[:1200].replace(key, "[REDACTED]")
        raise RuntimeError(f"HTTP {exc.code} {method} {path}: {err}") from None


def scrub(obj: object) -> object:
    """Redact likely secret fields recursively."""
    secret_keys = {
        "value",
        "password",
        "secret",
        "token",
        "key",
        "authorization",
        "DATABASE_URL",
        "JWT_SECRET",
        "S3_SECRET_KEY",
        "S3_ACCESS_KEY",
        "APP_DATABASE_URL",
        "OWNER_DATABASE_URL",
    }
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k.lower() in {s.lower() for s in secret_keys} or "secret" in k.lower() or "password" in k.lower():
                out[k] = "[REDACTED]" if v else v
            elif k in ("envVar",) and isinstance(v, dict):
                out[k] = {"key": v.get("key"), "value": "[REDACTED]" if v.get("value") else None}
            else:
                out[k] = scrub(v)
        return out
    if isinstance(obj, list):
        return [scrub(x) for x in obj]
    return obj


def main() -> int:
    key = load_env()["RENDER_API_KEY"]
    svc = api("GET", f"/services/{SERVICE_ID}", key)
    print("=== SERVICE KEYS ===")
    s = svc.get("service", svc) if isinstance(svc, dict) else {}
    if isinstance(s, dict):
        print("top_keys=" + ",".join(sorted(s.keys())))
        details = s.get("serviceDetails")
        if isinstance(details, dict):
            print("serviceDetails_keys=" + ",".join(sorted(details.keys())))
            for k in (
                "buildCommand",
                "startCommand",
                "dockerCommand",
                "dockerfilePath",
                "dockerContext",
                "env",
                "envSpecificDetails",
                "plan",
                "region",
                "runtime",
                "parentServer",
            ):
                if k in details:
                    print(f"details.{k}={details.get(k)!r}")
            esd = details.get("envSpecificDetails")
            if isinstance(esd, dict):
                print("envSpecificDetails=" + json.dumps(scrub(esd))[:800])

    dep = api("GET", f"/services/{SERVICE_ID}/deploys/{DEPLOY_ID}", key)
    d = dep.get("deploy", dep) if isinstance(dep, dict) else {}
    print("=== DEPLOY ===")
    if isinstance(d, dict):
        print(json.dumps(scrub({k: d.get(k) for k in d if k not in ("commit",)}), default=str)[:1200])
        if isinstance(d.get("commit"), dict):
            print(f"commit.id={d['commit'].get('id')}")
            print(f"commit.message={d['commit'].get('message')!r}")

    # Try deploy events
    try:
        events = api("GET", f"/services/{SERVICE_ID}/deploys/{DEPLOY_ID}/events", key)
        print("=== EVENTS ===")
        print(json.dumps(scrub(events), default=str)[:2000])
    except RuntimeError as exc:
        print(f"events: {exc}")

    # Fix build/start via correct nested shape for native python
    # Common Render shape:
    # serviceDetails.envSpecificDetails = { buildCommand, startCommand } for python
    attempts = [
        {
            "serviceDetails": {
                "envSpecificDetails": {
                    "buildCommand": "pip install -r backend/requirements.txt",
                    "startCommand": "python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $PORT",
                }
            }
        },
        {
            "serviceDetails": {
                "buildCommand": "pip install -r backend/requirements.txt",
                "startCommand": "python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $PORT",
                "healthCheckPath": "/api/healthz",
            }
        },
    ]
    for i, body in enumerate(attempts):
        try:
            api("PATCH", f"/services/{SERVICE_ID}", key, body)
            print(f"PATCH attempt {i}: ok")
        except RuntimeError as exc:
            print(f"PATCH attempt {i}: {exc}")

    svc2 = api("GET", f"/services/{SERVICE_ID}", key)
    s2 = svc2.get("service", svc2) if isinstance(svc2, dict) else {}
    if isinstance(s2, dict):
        details2 = s2.get("serviceDetails") if isinstance(s2.get("serviceDetails"), dict) else {}
        print("=== AFTER FIX ===")
        print(f"buildCommand={details2.get('buildCommand')!r}")
        print(f"startCommand={details2.get('startCommand')!r}")
        print(f"healthCheckPath={details2.get('healthCheckPath')!r}")
        esd = details2.get("envSpecificDetails")
        if isinstance(esd, dict):
            print(f"envSpecificDetails.buildCommand={esd.get('buildCommand')!r}")
            print(f"envSpecificDetails.startCommand={esd.get('startCommand')!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
