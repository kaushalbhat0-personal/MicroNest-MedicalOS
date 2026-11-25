"""Configure existing Render service for release/p3-7b-staging. Never print secrets."""
from __future__ import annotations

import json
import sys
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
            "User-Agent": "healthcare-os-p37b",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:  # noqa: S310
            raw = resp.read().decode()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        err = exc.read().decode(errors="replace")[:800].replace(key, "[REDACTED]")
        raise RuntimeError(f"HTTP {exc.code} {method} {path}: {err}") from None


def summarize_service(svc: dict) -> None:
    details = svc.get("serviceDetails") if isinstance(svc.get("serviceDetails"), dict) else {}
    print(
        f"name={svc.get('name')!r} type={svc.get('type')} "
        f"branch={svc.get('branch')!r} autoDeploy={svc.get('autoDeploy')} "
        f"url={details.get('url') or svc.get('url')!r} "
        f"repo={svc.get('repo')!r}"
    )


def main() -> int:
    env = load_env()
    key = env.get("RENDER_API_KEY", "")
    if not key:
        print("MISSING RENDER_API_KEY")
        return 2

    # Discover current service
    raw = api("GET", f"/services/{SERVICE_ID}", key)
    svc = raw.get("service", raw) if isinstance(raw, dict) else {}
    assert isinstance(svc, dict)
    print("=== BEFORE ===")
    summarize_service(svc)
    service_url = ""
    details = svc.get("serviceDetails") if isinstance(svc.get("serviceDetails"), dict) else {}
    service_url = str(details.get("url") or svc.get("url") or "")
    if not service_url:
        service_url = "https://micronest-medicalos.onrender.com"

    # Fetch existing env vars (names only in output)
    env_raw = api("GET", f"/services/{SERVICE_ID}/env-vars", key)
    existing: dict[str, str] = {}
    if isinstance(env_raw, list):
        for item in env_raw:
            # shapes: {envVar:{key,value}} or {key,value}
            ev = item.get("envVar", item) if isinstance(item, dict) else {}
            if isinstance(ev, dict) and ev.get("key"):
                existing[str(ev["key"])] = str(ev.get("value") or "")
    print(f"existing_env_var_count={len(existing)}")
    print("existing_env_keys=" + ",".join(sorted(existing.keys())[:80]))

    # Required application vars (actual Settings names)
    required = {
        "ENV": "preview",
        "DEPLOYMENT": "cloud",
        "COOKIE_SECURE": "true",
        "DB_SSL_REQUIRE": "true",
        "DEV_NOTIFICATIONS_ALLOW": "false",
        "NOTIFY_PROVIDER": "none",
        "SAAS_PAYMENT_PROVIDER": "mock",
        "APP_DATABASE_URL": env["APP_DATABASE_URL_CLOUD"],
        "JWT_SECRET": env["JWT_SECRET_CLOUD"],
        "API_PUBLIC_URL": service_url,
        "ALLOWED_ORIGINS": json.dumps([service_url]),
        "STORAGE_ADAPTER": "s3",
        "S3_ENDPOINT_URL": env["S3_ENDPOINT_URL"],
        "S3_BUCKET": env["S3_BUCKET"],
        "S3_REGION": env["S3_REGION"],
        "S3_ACCESS_KEY": env["S3_ACCESS_KEY"],
        "S3_SECRET_KEY": env["S3_SECRET_KEY"],
        "S3_USE_TLS": "true",
        "S3_ENSURE_BUCKET": "false",
    }
    # OWNER_DATABASE_URL intentionally omitted from long-running web service.

    # Never set RENDER_API_KEY on the service
    assert "RENDER_API_KEY" not in required

    merged = dict(existing)
    for k, v in required.items():
        merged[k] = v

    # Update service: branch + autoDeploy off (do not trigger deploy)
    # Render API: PATCH /services/{id}
    patch_body = {
        "branch": "release/p3-7b-staging",
        "autoDeploy": "no",
    }
    try:
        updated = api("PATCH", f"/services/{SERVICE_ID}", key, patch_body)
        print("PATCH service: ok")
    except RuntimeError as exc:
        print(f"PATCH service failed: {exc}")
        # try alternate autoDeploy boolean
        patch_body = {"branch": "release/p3-7b-staging", "autoDeploy": False}
        updated = api("PATCH", f"/services/{SERVICE_ID}", key, patch_body)
        print("PATCH service (bool autoDeploy): ok")

    # Put env vars — try bulk PUT
    env_payload = [{"key": k, "value": v} for k, v in sorted(merged.items())]
    try:
        api("PUT", f"/services/{SERVICE_ID}/env-vars", key, env_payload)
        print("PUT env-vars: ok")
    except RuntimeError as exc:
        print(f"PUT env-vars failed: {exc}")
        # fallback: update one-by-one via PUT /env-vars/{key}
        for k, v in required.items():
            try:
                api(
                    "PUT",
                    f"/services/{SERVICE_ID}/env-vars/{k}",
                    key,
                    {"value": v},
                )
                print(f"UPSERT {k}: ok")
            except RuntimeError as exc2:
                print(f"UPSERT {k}: FAIL {exc2}")
                return 1

    # Verify
    raw2 = api("GET", f"/services/{SERVICE_ID}", key)
    svc2 = raw2.get("service", raw2) if isinstance(raw2, dict) else {}
    print("=== AFTER ===")
    summarize_service(svc2 if isinstance(svc2, dict) else {})

    env_raw2 = api("GET", f"/services/{SERVICE_ID}/env-vars", key)
    keys_after: list[str] = []
    if isinstance(env_raw2, list):
        for item in env_raw2:
            ev = item.get("envVar", item) if isinstance(item, dict) else {}
            if isinstance(ev, dict) and ev.get("key"):
                keys_after.append(str(ev["key"]))
    keys_after_set = set(keys_after)
    print("env_keys_after_count=" + str(len(keys_after_set)))
    missing = [k for k in required if k not in keys_after_set]
    print("required_missing=" + (",".join(missing) if missing else "none"))
    if "RENDER_API_KEY" in keys_after_set:
        print("FAIL: RENDER_API_KEY was set on service")
        return 1
    if "OWNER_DATABASE_URL" in keys_after_set:
        print("NOTE: OWNER_DATABASE_URL present on service (pre-existing or set)")
    print("configured_required_keys=" + ",".join(sorted(required.keys())))
    print("DEPLOY_TRIGGERED=no")
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
