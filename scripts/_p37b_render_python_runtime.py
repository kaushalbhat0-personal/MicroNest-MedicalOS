"""Switch Render service to native Python runtime and redeploy. No secrets printed."""
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
    body = {
        "branch": BRANCH,
        "autoDeploy": "no",
        "serviceDetails": {
            "runtime": "python",
            "healthCheckPath": "/api/healthz",
            "envSpecificDetails": {
                "buildCommand": "pip install -r backend/requirements.txt",
                "startCommand": (
                    "python -m uvicorn app.main:app --app-dir backend "
                    "--host 0.0.0.0 --port $PORT"
                ),
            },
        },
    }
    try:
        api("PATCH", f"/services/{SERVICE_ID}", key, body)
        print("PATCH runtime=python: ok")
    except RuntimeError as exc:
        print(f"PATCH failed: {exc}")
        # fallback: keep docker, point at backend Dockerfile + override command for $PORT
        body2 = {
            "branch": BRANCH,
            "autoDeploy": "no",
            "serviceDetails": {
                "healthCheckPath": "/api/healthz",
                "envSpecificDetails": {
                    "dockerfilePath": "./backend/Dockerfile",
                    "dockerContext": ".",
                    "dockerCommand": (
                        "python -m uvicorn app.main:app --app-dir backend "
                        "--host 0.0.0.0 --port $PORT"
                    ),
                },
            },
        }
        api("PATCH", f"/services/{SERVICE_ID}", key, body2)
        print("PATCH docker Dockerfile path+command: ok")

    svc = api("GET", f"/services/{SERVICE_ID}", key)
    s = svc.get("service", svc) if isinstance(svc, dict) else {}
    details = s.get("serviceDetails") if isinstance(s, dict) else {}
    if isinstance(details, dict):
        print(f"runtime={details.get('runtime')!r} env={details.get('env')!r}")
        print(f"healthCheckPath={details.get('healthCheckPath')!r}")
        esd = details.get("envSpecificDetails")
        if isinstance(esd, dict):
            print(
                f"buildCommand={esd.get('buildCommand')!r} "
                f"startCommand={esd.get('startCommand')!r} "
                f"dockerfilePath={esd.get('dockerfilePath')!r}"
            )

    # Ensure autoDeploy still no
    if isinstance(s, dict):
        print(f"branch={s.get('branch')!r} autoDeploy={s.get('autoDeploy')}")
        if s.get("branch") != BRANCH or str(s.get("autoDeploy")).lower() not in ("no", "false"):
            print("STOP: branch/autoDeploy incorrect")
            return 2

    dep = api("POST", f"/services/{SERVICE_ID}/deploys", key, {"clearCache": "clear"})
    d = dep.get("deploy", dep) if isinstance(dep, dict) else {}
    deploy_id = d.get("id") if isinstance(d, dict) else None
    print(f"DEPLOY_TRIGGERED id={deploy_id}")
    if not deploy_id:
        return 3

    terminal_fail = {
        "build_failed",
        "update_failed",
        "canceled",
        "deactivated",
        "pre_deploy_failed",
    }
    status = ""
    commit = ""
    for i in range(120):
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
        if status == "live":
            break
        if status in terminal_fail:
            break

    print(f"DEPLOY_TERMINAL status={status} id={deploy_id} commit={commit}")
    meta = {
        "deploy_id": deploy_id,
        "status": status,
        "commit": commit,
        "service_url": "https://micronest-medicalos.onrender.com",
        "branch": BRANCH,
    }
    (ROOT / "scripts" / "_p37b_last_deploy.json").write_text(json.dumps(meta), encoding="utf-8")
    return 0 if status == "live" else 11


if __name__ == "__main__":
    raise SystemExit(main())
