"""Discover Render services using RENDER_API_KEY from .env. Never print secrets."""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_env() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def api(method: str, path: str, key: str, body: dict | None = None) -> object:
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
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
            raw = resp.read().decode()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:  # type: ignore[name-defined]
        err = exc.read().decode(errors="replace")[:500]
        # scrub bearer if echoed
        err = err.replace(key, "[REDACTED]")
        raise RuntimeError(f"HTTP {exc.code}: {err}") from None


def main() -> int:
    import urllib.error  # noqa: F401 — used in api

    env = load_env()
    key = env.get("RENDER_API_KEY", "")
    if not key:
        print("MISSING: RENDER_API_KEY")
        return 2
    print("RENDER_API_KEY: PRESENT (not printed)")
    services = api("GET", "/services?limit=50", key)
    if not isinstance(services, list):
        print(f"UNEXPECTED payload type={type(services).__name__}")
        return 1
    print(f"service_count={len(services)}")
    matches = []
    for item in services:
        svc = item.get("service", item) if isinstance(item, dict) else {}
        if not isinstance(svc, dict):
            continue
        sid = svc.get("id", "")
        name = svc.get("name", "")
        stype = svc.get("type", "")
        repo = (svc.get("repo") or "") if isinstance(svc.get("repo"), str) else ""
        # nested repo object in some API versions
        if isinstance(svc.get("repo"), dict):
            repo = str(svc["repo"].get("url") or svc["repo"].get("name") or "")
        branch = svc.get("branch", "")
        url = svc.get("serviceDetails", {}) if isinstance(svc.get("serviceDetails"), dict) else {}
        url = url.get("url") or svc.get("url") or ""
        auto = svc.get("autoDeploy")
        print(
            f"- id={sid} name={name!r} type={stype} branch={branch!r} "
            f"autoDeploy={auto} url={url!r} repo={repo!r}"
        )
        name_l = str(name).lower()
        repo_l = str(repo).lower()
        if (
            "healthcare" in name_l
            or "micronest" in name_l
            or "medical" in name_l
            or "staging" in name_l
            or "micronest-medical" in repo_l
        ):
            matches.append(svc)
    print(f"candidate_matches={len(matches)}")
    if len(matches) == 1:
        m = matches[0]
        print(f"SELECTED_ID={m.get('id')}")
        print(f"SELECTED_NAME={m.get('name')}")
        Path(ROOT / "scripts" / "_p37b_selected_service_id.txt").write_text(
            str(m.get("id") or ""), encoding="utf-8"
        )
    elif len(matches) == 0 and len(services) == 1:
        item = services[0]
        m = item.get("service", item) if isinstance(item, dict) else {}
        print(f"FALLBACK_SINGLE_SERVICE id={m.get('id')} name={m.get('name')!r}")
        Path(ROOT / "scripts" / "_p37b_selected_service_id.txt").write_text(
            str(m.get("id") or ""), encoding="utf-8"
        )
    else:
        print("STOP: ambiguous or zero matches — need user confirmation")
        return 3
    return 0


if __name__ == "__main__":
    # late import for HTTPError in api
    import urllib.error  # noqa: E402

    sys.modules[__name__].urllib = urllib  # type: ignore[attr-defined]
    # patch api to use urllib.error
    def api2(method: str, path: str, key: str, body: dict | None = None) -> object:
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
            with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
                raw = resp.read().decode()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            err = exc.read().decode(errors="replace")[:500].replace(key, "[REDACTED]")
            raise RuntimeError(f"HTTP {exc.code}: {err}") from None

    globals()["api"] = api2
    raise SystemExit(main())
