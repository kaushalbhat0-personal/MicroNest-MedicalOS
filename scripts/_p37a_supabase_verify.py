"""P3.7A Supabase staging verification. Never prints secret values."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def redact_url(url: str) -> str:
    if not url:
        return "EMPTY"
    raw = url.replace("postgresql+psycopg2://", "postgresql://", 1)
    u = urlparse(raw)
    host = u.hostname or "?"
    user = u.username or "?"
    if user not in ("hos_owner", "hos_app", "postgres") and not user.startswith("postgres."):
        user = "custom"
    if user.startswith("postgres."):
        user = "postgres.<project_ref>"
    return f"{u.scheme}://{user}@{host}:{u.port}{u.path}?{('sslmode' if 'sslmode' in (u.query or '') else 'no-ssl')}"


def http_json(url: str, token: str) -> object:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "healthcare-os-p37a",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 — fixed Supabase API host
        return json.loads(resp.read().decode())


def main() -> int:
    env = load_env(ROOT / ".env")
    ref = env.get("SUPABASE_PROJECT_REF", "").strip()
    if ref.startswith("http"):
        print("FAIL: SUPABASE_PROJECT_REF must be the project ref id, not a URL")
        return 2
    token = env.get("SUPABASE_ACCESS_TOKEN", "")
    if not token:
        print("MISSING: SUPABASE_ACCESS_TOKEN")
        return 2
    if not token.startswith("sbp_"):
        print("WARN: SUPABASE_ACCESS_TOKEN does not look like a personal access token (sbp_*)")

    print("=== Management API: list projects (names/refs/regions/status only) ===")
    try:
        projects = http_json("https://api.supabase.com/v1/projects", token)
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: management API list projects: {type(exc).__name__}")
        return 1
    if not isinstance(projects, list):
        print("FAIL: unexpected projects payload type")
        return 1
    match = None
    print(f"accessible_project_count={len(projects)}")
    for p in projects:
        if not isinstance(p, dict):
            continue
        pref = str(p.get("id") or p.get("ref") or "")
        name = str(p.get("name") or "")
        region = str(p.get("region") or "")
        status = str(p.get("status") or "")
        print(f"- ref={pref} name={name!r} region={region} status={status}")
        if pref == ref:
            match = p
    if match is None:
        print(f"FAIL: SUPABASE_PROJECT_REF={ref!r} not found in accessible projects — STOP")
        return 3
    print("MATCHED_STAGING_CANDIDATE=yes")
    print(f"matched_name={match.get('name')!r}")
    print(f"matched_region={match.get('region')}")
    print(f"matched_status={match.get('status')}")
    print(f"SUPABASE_URL={env.get('SUPABASE_URL') or f'https://{ref}.supabase.co'}")
    print(f"OWNER_DATABASE_URL_CLOUD shape: {redact_url(env.get('OWNER_DATABASE_URL_CLOUD', ''))}")
    print(f"APP_DATABASE_URL_CLOUD shape: {redact_url(env.get('APP_DATABASE_URL_CLOUD', ''))}")
    print(f"S3_ENDPOINT host path only: set={bool(env.get('S3_ENDPOINT_URL'))}")
    print(f"S3_BUCKET={env.get('S3_BUCKET')!r}")
    print(f"S3_REGION={env.get('S3_REGION')!r}")
    print(
        "credential_kinds: "
        f"SUPABASE_ACCESS_TOKEN=management-pat "
        f"S3_ACCESS_KEY={'set' if env.get('S3_ACCESS_KEY') else 'missing'} "
        f"S3_SECRET_KEY={'set' if env.get('S3_SECRET_KEY') else 'missing'}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
