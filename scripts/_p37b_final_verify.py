"""Final Render identity + env shape verification. No secret values printed."""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlparse

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


def main() -> None:
    env = load_env()
    key = env["RENDER_API_KEY"]
    headers = {
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "User-Agent": "p37b-verify",
    }
    with urllib.request.urlopen(  # noqa: S310
        urllib.request.Request(f"https://api.render.com/v1/services/{SERVICE_ID}", headers=headers),
        timeout=60,
    ) as resp:
        svc = json.loads(resp.read().decode())
    s = svc.get("service", svc)
    details = s.get("serviceDetails") or {}
    esd = details.get("envSpecificDetails") or {}
    print(f"name={s.get('name')}")
    print(f"id={s.get('id')}")
    print(f"url={details.get('url')}")
    print(f"branch={s.get('branch')}")
    print(f"autoDeploy={s.get('autoDeploy')}")
    print(f"runtime={details.get('runtime')} env={details.get('env')}")
    print(f"health={details.get('healthCheckPath')}")
    print(f"build={esd.get('buildCommand')}")
    print(f"start={esd.get('startCommand')}")

    with urllib.request.urlopen(  # noqa: S310
        urllib.request.Request(
            f"https://api.render.com/v1/services/{SERVICE_ID}/env-vars", headers=headers
        ),
        timeout=60,
    ) as resp:
        items = json.loads(resp.read().decode())

    public_keys = {
        "ALLOWED_ORIGINS",
        "API_PUBLIC_URL",
        "ENV",
        "DEPLOYMENT",
        "STORAGE_ADAPTER",
        "S3_BUCKET",
        "S3_REGION",
        "S3_ENSURE_BUCKET",
        "S3_USE_TLS",
        "COOKIE_SECURE",
        "DB_SSL_REQUIRE",
        "DEV_NOTIFICATIONS_ALLOW",
        "NOTIFY_PROVIDER",
        "SAAS_PAYMENT_PROVIDER",
        "PYTHON_VERSION",
    }
    for item in items:
        ev = item.get("envVar", item)
        k = ev.get("key")
        v = ev.get("value") or ""
        if k in public_keys:
            print(f"{k}={v}")
        elif k == "JWT_SECRET":
            local = env.get("JWT_SECRET", "")
            cloud = env.get("JWT_SECRET_CLOUD", "")
            print(
                f"JWT_SECRET length={len(v)} "
                f"differs_from_local_JWT_SECRET={v != local} "
                f"matches_JWT_SECRET_CLOUD={v == cloud} "
                f"min_32={len(v) >= 32}"
            )
        elif k == "APP_DATABASE_URL":
            p = urlparse(v)
            print(
                f"APP_DATABASE_URL user={p.username} host={p.hostname} "
                f"db={(p.path or '').lstrip('/')} ssl={parse_qs(p.query).get('sslmode')}"
            )
        elif k in ("S3_ACCESS_KEY", "S3_SECRET_KEY", "S3_ENDPOINT_URL"):
            print(f"{k} present=True length={len(v)}")
    names = sorted(
        str((i.get("envVar", i) or {}).get("key"))
        for i in items
        if isinstance(i, dict)
    )
    print(f"all_env_names={names}")
    print(f"forbidden_present={sorted(set(names) & {'RENDER_API_KEY', 'OWNER_DATABASE_URL'})}")


if __name__ == "__main__":
    main()
