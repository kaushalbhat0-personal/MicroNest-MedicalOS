"""Exclude local-only deps from Render build; pin Python 3.10; redeploy.

No secret values printed.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE_ID = "srv-dc2tmb49v7es73dkqc9g"
BRANCH = "release/p3-7b-staging"
BUILD_CMD = (
    "sed '/^pgserver/d;/^pytest/d;/^ruff/d;/^mypy/d' "
    "backend/requirements.txt > /tmp/requirements-runtime.txt "
    "&& pip install -r /tmp/requirements-runtime.txt"
)
START_CMD = (
    "python -m uvicorn app.main:app --app-dir backend "
    "--host 0.0.0.0 --port $PORT"
)


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
        err = exc.read().decode(errors="replace")[:1000].replace(key, "[REDACTED]")
        raise RuntimeError(f"HTTP {exc.code} {method} {path}: {err}") from None


def main() -> int:
    key = load_env()["RENDER_API_KEY"]

    # Merge PYTHON_VERSION without wiping other vars
    raw_vars = api("GET", f"/services/{SERVICE_ID}/env-vars", key)
    if not isinstance(raw_vars, list):
        print("STOP: unexpected env-vars response")
        return 2
    merged: dict[str, str] = {}
    for item in raw_vars:
        if not isinstance(item, dict):
            continue
        ev = item.get("envVar", item)
        if isinstance(ev, dict) and ev.get("key"):
            merged[str(ev["key"])] = str(ev.get("value") or "")
    names_before = sorted(merged.keys())
    print(f"env_names_before={names_before}")
    if "PYTHON_VERSION" not in merged:
        merged["PYTHON_VERSION"] = "3.10.14"
        print("added PYTHON_VERSION=3.10.14 (value intentionally listed; not a secret)")
    put_body = [{"key": k, "value": v} for k, v in sorted(merged.items())]
    api("PUT", f"/services/{SERVICE_ID}/env-vars", key, put_body)
    after = api("GET", f"/services/{SERVICE_ID}/env-vars", key)
    names_after = sorted(
        str((i.get("envVar", i) or {}).get("key"))
        for i in (after if isinstance(after, list) else [])
        if isinstance(i, dict)
    )
    print(f"env_names_after={names_after}")
    required = {
        "APP_DATABASE_URL",
        "JWT_SECRET",
        "API_PUBLIC_URL",
        "ALLOWED_ORIGINS",
        "STORAGE_ADAPTER",
        "S3_ENDPOINT_URL",
        "S3_BUCKET",
        "S3_REGION",
        "S3_ACCESS_KEY",
        "S3_SECRET_KEY",
        "ENV",
        "DEPLOYMENT",
        "DB_SSL_REQUIRE",
        "COOKIE_SECURE",
        "PYTHON_VERSION",
    }
    missing = sorted(required - set(names_after))
    if missing:
        print(f"STOP: missing required env names: {missing}")
        return 3
    forbidden = {"RENDER_API_KEY", "OWNER_DATABASE_URL"}
    present_forbidden = sorted(forbidden & set(names_after))
    if present_forbidden:
        print(f"STOP: forbidden runtime vars present: {present_forbidden}")
        return 4

    # Patch build/start
    api(
        "PATCH",
        f"/services/{SERVICE_ID}",
        key,
        {
            "branch": BRANCH,
            "autoDeploy": "no",
            "serviceDetails": {
                "runtime": "python",
                "healthCheckPath": "/api/healthz",
                "envSpecificDetails": {
                    "buildCommand": BUILD_CMD,
                    "startCommand": START_CMD,
                },
            },
        },
    )
    svc = api("GET", f"/services/{SERVICE_ID}", key)
    s = svc.get("service", svc) if isinstance(svc, dict) else {}
    details = s.get("serviceDetails") if isinstance(s, dict) else {}
    esd = details.get("envSpecificDetails") if isinstance(details, dict) else {}
    print(f"branch={s.get('branch')!r} autoDeploy={s.get('autoDeploy')}")
    print(f"runtime={details.get('runtime')!r}")
    print(f"buildCommand={esd.get('buildCommand')!r}")
    print(f"startCommand={esd.get('startCommand')!r}")
    if s.get("branch") != BRANCH or str(s.get("autoDeploy")).lower() not in ("no", "false"):
        print("STOP: branch/autoDeploy incorrect")
        return 5

    dep = api("POST", f"/services/{SERVICE_ID}/deploys", key, {"clearCache": "clear"})
    d = dep.get("deploy", dep) if isinstance(dep, dict) else {}
    deploy_id = d.get("id") if isinstance(d, dict) else None
    print(f"DEPLOY_TRIGGERED id={deploy_id}")
    if not deploy_id:
        return 6

    terminal_fail = {
        "build_failed",
        "update_failed",
        "canceled",
        "deactivated",
        "pre_deploy_failed",
    }
    status = ""
    commit = ""
    for i in range(180):
        time.sleep(15)
        draw = api("GET", f"/services/{SERVICE_ID}/deploys/{deploy_id}", key)
        dd = draw.get("deploy", draw) if isinstance(draw, dict) else {}
        if not isinstance(dd, dict):
            continue
        status = str(dd.get("status") or "")
        c = dd.get("commit")
        if isinstance(c, dict):
            commit = str(c.get("id") or "")
        print(f"poll[{i}] status={status} commit={commit[:12] if commit else ''}")
        if status == "live" or status in terminal_fail:
            break

    print(f"DEPLOY_TERMINAL status={status} id={deploy_id} commit={commit}")
    meta = {
        "deploy_id": deploy_id,
        "status": status,
        "commit": commit,
        "service_url": "https://micronest-medicalos.onrender.com",
        "branch": BRANCH,
        "build_command_note": "excludes pgserver/pytest/ruff/mypy (local-only)",
        "python_version": "3.10.14",
    }
    (ROOT / "scripts" / "_p37b_last_deploy.json").write_text(json.dumps(meta), encoding="utf-8")
    return 0 if status == "live" else 11


if __name__ == "__main__":
    raise SystemExit(main())
