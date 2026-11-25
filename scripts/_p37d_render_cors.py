"""Add exact Vercel Preview origin to Render staging ALLOWED_ORIGINS; redeploy if changed."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE_ID = "srv-dc2tmb49v7es73dkqc9g"
API_ORIGIN = "https://micronest-medicalos.onrender.com"
PREVIEW_ORIGIN = "https://micro-nest-medical-8eeq5wwe6-kaushal-bhats-projects.vercel.app"
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
            "User-Agent": "healthcare-os-p37d",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:  # noqa: S310
            raw = resp.read().decode()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        err = exc.read().decode(errors="replace")[:800].replace(key, "[REDACTED]")
        raise RuntimeError(f"HTTP {exc.code} {method} {path}: {err}") from None


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
        print("MISSING RENDER_API_KEY")
        return 2

    svc_raw = api("GET", f"/services/{SERVICE_ID}", key)
    svc = svc_raw.get("service", svc_raw) if isinstance(svc_raw, dict) else {}
    assert isinstance(svc, dict)
    print(f"service={svc.get('name')!r} branch={svc.get('branch')!r} autoDeploy={svc.get('autoDeploy')}")
    if svc.get("branch") != BRANCH:
        print("STOP: unexpected Render branch")
        return 3
    if str(svc.get("autoDeploy")).lower() not in ("no", "false"):
        print("STOP: autoDeploy must remain disabled")
        return 3

    existing = list_env(key)
    current = existing.get("ALLOWED_ORIGINS", "")
    print(f"ALLOWED_ORIGINS_before={current}")

    # Parse current list
    try:
        origins = json.loads(current) if current.strip().startswith("[") else [current.strip()]
    except json.JSONDecodeError:
        origins = [o.strip() for o in current.split(",") if o.strip()]

    if not isinstance(origins, list):
        print("STOP: ALLOWED_ORIGINS not a list")
        return 4
    if "*" in origins or any(o == "*" for o in origins):
        print("STOP: wildcard present")
        return 4

    desired = []
    for o in origins:
        if o and o not in desired:
            desired.append(o)
    for o in (API_ORIGIN, PREVIEW_ORIGIN):
        if o not in desired:
            desired.append(o)

    new_val = json.dumps(desired)
    print(f"ALLOWED_ORIGINS_after={new_val}")
    if "*" in new_val:
        print("STOP: refused wildcard")
        return 4

    changed = current.strip() != new_val.strip()
    print(f"cors_changed={changed}")

    if changed:
        merged = dict(existing)
        merged["ALLOWED_ORIGINS"] = new_val
        # Never introduce forbidden keys
        for forbidden in ("RENDER_API_KEY", "SUPABASE_ACCESS_TOKEN"):
            if forbidden in merged:
                print(f"STOP: refusing to write {forbidden} back to service")
                return 5
        payload = [{"key": k, "value": v} for k, v in sorted(merged.items())]
        api("PUT", f"/services/{SERVICE_ID}/env-vars", key, payload)
        print("PUT env-vars: ok (ALLOWED_ORIGINS updated; others preserved)")

        # Controlled redeploy
        try:
            dep = api("POST", f"/services/{SERVICE_ID}/deploys", key, {"clearCache": "do_not_clear"})
        except RuntimeError:
            dep = api("POST", f"/services/{SERVICE_ID}/deploys", key, {})
        deploy = dep.get("deploy", dep) if isinstance(dep, dict) else {}
        deploy_id = deploy.get("id") if isinstance(deploy, dict) else None
        print(f"redeploy_triggered id={deploy_id}")

        deadline = time.time() + 900
        while time.time() < deadline:
            deploys = api("GET", f"/services/{SERVICE_ID}/deploys?limit=5", key)
            rows = deploys if isinstance(deploys, list) else []
            status = None
            commit = None
            for row in rows:
                d = row.get("deploy", row) if isinstance(row, dict) else {}
                if deploy_id and d.get("id") != deploy_id:
                    continue
                status = d.get("status")
                commit = (d.get("commit") or {}).get("id") if isinstance(d.get("commit"), dict) else d.get("commitId")
                print(f"deploy_status={status} commit={str(commit)[:12] if commit else None}")
                break
            if status in ("live", "succeeded", "available"):
                break
            if status in ("failed", "canceled", "deactivated", "build_failed", "update_failed"):
                print(f"STOP: deploy failed status={status}")
                return 6
            time.sleep(20)
        else:
            print("TIMEOUT waiting for Render redeploy")
            return 7
    else:
        print("no_redeploy_needed")

    # Health checks
    for path in ("/api/healthz", "/api/readyz"):
        url = f"{API_ORIGIN}{path}"
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310
                print(f"health {path} status={resp.status}")
        except Exception as exc:  # noqa: BLE001
            print(f"health {path} ERROR {type(exc).__name__}: {exc}")
            return 8

    # Confirm env after
    after = list_env(key)
    print(f"ALLOWED_ORIGINS_final={after.get('ALLOWED_ORIGINS')}")
    if PREVIEW_ORIGIN not in (after.get("ALLOWED_ORIGINS") or ""):
        print("STOP: preview origin missing after update")
        return 9
    if "*" in (after.get("ALLOWED_ORIGINS") or ""):
        print("STOP: wildcard after update")
        return 9

    # Confirm autoDeploy still off
    svc2_raw = api("GET", f"/services/{SERVICE_ID}", key)
    svc2 = svc2_raw.get("service", svc2_raw) if isinstance(svc2_raw, dict) else {}
    print(f"autoDeploy_final={svc2.get('autoDeploy')} branch_final={svc2.get('branch')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
