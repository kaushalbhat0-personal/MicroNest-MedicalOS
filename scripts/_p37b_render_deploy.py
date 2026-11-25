"""Configure + validate + deploy Render staging. Never print secret values."""
from __future__ import annotations

import json
import secrets
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SERVICE_ID = "srv-dc2tmb49v7es73dkqc9g"
BRANCH = "release/p3-7b-staging"
EXPECTED_URL = "https://micronest-medicalos.onrender.com"


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
        err = exc.read().decode(errors="replace")[:800].replace(key, "[REDACTED]")
        raise RuntimeError(f"HTTP {exc.code} {method} {path}: {err}") from None


def shape_db_url(url: str) -> dict[str, object]:
    raw = url.replace("postgresql+psycopg2://", "postgresql://", 1)
    u = urlparse(raw)
    user = u.username or ""
    role = user.split(".")[0] if "." in user else user
    return {
        "scheme": "postgresql+psycopg2" if "psycopg2" in url else u.scheme,
        "role": role,
        "host_class": "supabase-pooler" if u.hostname and "pooler" in u.hostname else (u.hostname or ""),
        "port": u.port,
        "db": (u.path or "").lstrip("/"),
        "sslmode_require": "sslmode=require" in (u.query or ""),
    }


def redact_s3_endpoint(url: str) -> str:
    u = urlparse(url)
    return f"{u.scheme}://{u.hostname}{u.path}"


def get_service(key: str) -> dict:
    raw = api("GET", f"/services/{SERVICE_ID}", key)
    svc = raw.get("service", raw) if isinstance(raw, dict) else {}
    if not isinstance(svc, dict):
        raise RuntimeError("unexpected service payload")
    return svc


def list_env(key: str) -> dict[str, str]:
    raw = api("GET", f"/services/{SERVICE_ID}/env-vars", key)
    out: dict[str, str] = {}
    if isinstance(raw, list):
        for item in raw:
            ev = item.get("envVar", item) if isinstance(item, dict) else {}
            if isinstance(ev, dict) and ev.get("key"):
                out[str(ev["key"])] = str(ev.get("value") or "")
    return out


def main() -> int:
    env = load_env()
    key = env.get("RENDER_API_KEY", "")
    if not key:
        print("STOP: RENDER_API_KEY missing")
        return 2

    # --- Phase 2 inspect ---
    svc = get_service(key)
    details = svc.get("serviceDetails") if isinstance(svc.get("serviceDetails"), dict) else {}
    print("=== SERVICE ===")
    print(f"id={svc.get('id')}")
    print(f"name={svc.get('name')!r}")
    print(f"type={svc.get('type')}")
    print(f"repo={svc.get('repo')!r}")
    print(f"branch={svc.get('branch')!r}")
    print(f"autoDeploy={svc.get('autoDeploy')}")
    print(f"url={details.get('url')!r}")
    print(f"buildCommand={details.get('buildCommand')!r}")
    print(f"startCommand={details.get('startCommand')!r}")
    print(f"healthCheckPath={details.get('healthCheckPath')!r}")

    if svc.get("id") != SERVICE_ID and svc.get("name") != "MicroNest-MedicalOS":
        # id from path; name must match
        pass
    if svc.get("name") != "MicroNest-MedicalOS":
        print("STOP: service name mismatch")
        return 3

    existing = list_env(key)
    print(f"existing_env_count={len(existing)}")
    print("existing_keys=" + ",".join(sorted(existing.keys())))

    # Fresh staging JWT (do not reuse local/dev JWT_SECRET)
    jwt = secrets.token_urlsafe(48)
    if len(jwt.encode()) < 32:
        print("STOP: JWT generation failed strength check")
        return 4
    print("JWT_SECRET: generated_fresh_staging (not printed)")

    app_db = env.get("APP_DATABASE_URL_CLOUD", "")
    shape = shape_db_url(app_db)
    print(f"APP_DATABASE_URL_CLOUD_shape={shape}")
    if shape["role"] != "hos_app":
        print("STOP: APP_DATABASE_URL_CLOUD must use hos_app")
        return 5
    if not shape["sslmode_require"]:
        print("STOP: sslmode=require missing")
        return 5
    if "preview" not in str(shape["db"]):
        print("STOP: database name must contain preview for ENV=preview")
        return 5
    if shape["host_class"] != "supabase-pooler":
        print("STOP: expected session pooler host")
        return 5

    for req in ("S3_ENDPOINT_URL", "S3_BUCKET", "S3_REGION", "S3_ACCESS_KEY", "S3_SECRET_KEY"):
        if not env.get(req):
            print(f"STOP: missing local {req}")
            return 6
    print(f"S3_ENDPOINT={redact_s3_endpoint(env['S3_ENDPOINT_URL'])}")
    print(f"S3_BUCKET={env['S3_BUCKET']!r}")
    print(f"S3_REGION={env['S3_REGION']!r}")

    # CORS: boot requires non-empty ALLOWED_ORIGINS; use API origin only (no invented Vercel)
    origins = json.dumps([EXPECTED_URL])
    print(f"ALLOWED_ORIGINS_decision={origins} (API origin only; no Vercel yet)")

    required = {
        "ENV": "preview",
        "DEPLOYMENT": "cloud",
        "COOKIE_SECURE": "true",
        "DB_SSL_REQUIRE": "true",
        "DEV_NOTIFICATIONS_ALLOW": "false",
        "NOTIFY_PROVIDER": "none",
        "SAAS_PAYMENT_PROVIDER": "mock",
        "APP_DATABASE_URL": app_db,
        "JWT_SECRET": jwt,
        "API_PUBLIC_URL": EXPECTED_URL,
        "ALLOWED_ORIGINS": origins,
        "STORAGE_ADAPTER": "s3",
        "S3_ENDPOINT_URL": env["S3_ENDPOINT_URL"],
        "S3_BUCKET": env["S3_BUCKET"],
        "S3_REGION": env["S3_REGION"],
        "S3_ACCESS_KEY": env["S3_ACCESS_KEY"],
        "S3_SECRET_KEY": env["S3_SECRET_KEY"],
        "S3_USE_TLS": "true",
        "S3_ENSURE_BUCKET": "false",
    }
    # OWNER_DATABASE_URL / RENDER_API_KEY intentionally omitted
    for forbidden in ("RENDER_API_KEY", "SUPABASE_ACCESS_TOKEN", "OWNER_DATABASE_URL"):
        if forbidden in required:
            print(f"STOP: refused to set {forbidden}")
            return 7

    merged = dict(existing)
    for k, v in required.items():
        merged[k] = v
    # Ensure we don't keep OWNER on runtime if it was never needed — leave pre-existing
    # OWNER_DATABASE_URL if operator set it; document presence only
    if "OWNER_DATABASE_URL" in merged:
        print("NOTE: OWNER_DATABASE_URL already present on service — preserved, not used by app boot")
    if "RENDER_API_KEY" in merged:
        print("STOP: RENDER_API_KEY found in service env — refusing to proceed until removed")
        return 7

    # Patch service branch + autoDeploy + build/start/health if needed
    patch: dict[str, object] = {
        "branch": BRANCH,
        "autoDeploy": "no",
    }
    # serviceDetails fields may need nested update — try top-level first
    # Render uses serviceDetails for buildCommand in GET; PATCH may accept:
    patch_details = {
        "buildCommand": "pip install -r backend/requirements.txt",
        "startCommand": "python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $PORT",
        "healthCheckPath": "/api/healthz",
    }
    # First patch branch/autodeploy
    api("PATCH", f"/services/{SERVICE_ID}", key, patch)
    print("PATCH branch+autoDeploy: ok")

    # Try patching build/start via serviceDetails
    try:
        api("PATCH", f"/services/{SERVICE_ID}", key, {"serviceDetails": patch_details})
        print("PATCH serviceDetails build/start/health: ok")
    except RuntimeError as exc:
        print(f"PATCH serviceDetails skipped/failed: {str(exc)[:200]}")

    # Merge env vars via PUT (full replace of service-level vars with merged set)
    payload = [{"key": k, "value": v} for k, v in sorted(merged.items())]
    api("PUT", f"/services/{SERVICE_ID}/env-vars", key, payload)
    print("PUT env-vars merged: ok")

    # --- Phase 3 validate ---
    svc2 = get_service(key)
    details2 = svc2.get("serviceDetails") if isinstance(svc2.get("serviceDetails"), dict) else {}
    print("=== PRE-DEPLOY VERIFY ===")
    print(f"branch={svc2.get('branch')!r}")
    print(f"autoDeploy={svc2.get('autoDeploy')}")
    print(f"buildCommand={details2.get('buildCommand')!r}")
    print(f"startCommand={details2.get('startCommand')!r}")
    print(f"healthCheckPath={details2.get('healthCheckPath')!r}")

    if svc2.get("branch") != BRANCH:
        print("STOP: branch not set to release/p3-7b-staging")
        return 8
    if str(svc2.get("autoDeploy")).lower() not in ("no", "false"):
        print("STOP: autoDeploy not disabled")
        return 8

    env_after = list_env(key)
    missing = [k for k in required if k not in env_after]
    print("required_present=" + ("yes" if not missing else "no missing=" + ",".join(missing)))
    if missing:
        return 9
    # Validate shapes from remote without printing values
    remote_db = shape_db_url(env_after["APP_DATABASE_URL"])
    print(f"remote_APP_DATABASE_URL_shape={remote_db}")
    if remote_db["role"] != "hos_app" or not remote_db["sslmode_require"]:
        print("STOP: remote APP_DATABASE_URL shape invalid")
        return 9
    if env_after.get("ALLOWED_ORIGINS") == "*" or '"*"' in env_after.get("ALLOWED_ORIGINS", ""):
        print("STOP: wildcard CORS")
        return 9
    if len(env_after.get("JWT_SECRET", "").encode()) < 32:
        print("STOP: remote JWT_SECRET too short")
        return 9
    if env_after.get("STORAGE_ADAPTER") != "s3":
        print("STOP: STORAGE_ADAPTER not s3")
        return 9
    if "RENDER_API_KEY" in env_after:
        print("STOP: RENDER_API_KEY on service")
        return 9
    print("PREDEPLOY_OK")

    # Persist JWT into local JWT_SECRET_CLOUD without printing (for operator continuity)
    # Actually user said never commit; updating .env is ok for local mapping — do carefully
    # Skip writing .env to avoid accidental leakage in diffs; JWT lives on Render only.

    # --- Phase 4 deploy ---
    # POST /services/{id}/deploys  {clearCache: ...}
    deploy_body = {"clearCache": "do_not_clear"}
    try:
        dep = api("POST", f"/services/{SERVICE_ID}/deploys", key, deploy_body)
    except RuntimeError:
        dep = api("POST", f"/services/{SERVICE_ID}/deploys", key, {})
    # normalize
    deploy = dep.get("deploy", dep) if isinstance(dep, dict) else {}
    deploy_id = deploy.get("id") if isinstance(deploy, dict) else None
    print(f"DEPLOY_TRIGGERED id={deploy_id}")
    if not deploy_id:
        print(f"STOP: no deploy id payload_type={type(dep).__name__}")
        return 10

    # Poll deploy
    terminal = {"live", "deactivated", "build_failed", "update_failed", "canceled", "pre_deploy_failed"}
    status = ""
    commit = ""
    for _ in range(90):  # ~15 min
        time.sleep(10)
        draw = api("GET", f"/services/{SERVICE_ID}/deploys/{deploy_id}", key)
        d = draw.get("deploy", draw) if isinstance(draw, dict) else {}
        if not isinstance(d, dict):
            continue
        status = str(d.get("status") or "")
        commit = str(d.get("commit", {}).get("id") if isinstance(d.get("commit"), dict) else d.get("commitId") or "")
        created = d.get("createdAt")
        updated = d.get("updatedAt")
        print(f"deploy_poll status={status} commit={commit[:12] if commit else ''} created={created} updated={updated}")
        if status in terminal or status == "live":
            break
    print(f"DEPLOY_TERMINAL status={status} id={deploy_id} commit={commit}")
    if status != "live":
        print("STOP: deploy did not reach live")
        return 11

    # write deploy meta for smoke script
    meta = {
        "deploy_id": deploy_id,
        "status": status,
        "commit": commit,
        "service_url": EXPECTED_URL,
        "branch": BRANCH,
    }
    (ROOT / "scripts" / "_p37b_last_deploy.json").write_text(json.dumps(meta), encoding="utf-8")
    print("DEPLOY_LIVE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
