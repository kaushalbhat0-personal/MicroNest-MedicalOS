"""Deploy local P3.7D.2 tree as Vercel Preview (not Production). Never prints secrets."""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCOPE = "kaushal-bhats-projects"
PROJECT_ID = "prj_7TvXFLPGYq59spXXgEdjb0xkfr9c"
TEAM_ID = "team_5sXYYqiUCdvjfuzfdRK11yiS"


def run(cmd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, shell=True, check=False)


def vercel_api(path: str) -> object:
    proc = run(f"npx vercel api {path} --scope {SCOPE}")
    raw = (proc.stdout or "") + (proc.stderr or "")
    start = min(i for i in (raw.find("{"), raw.find("[")) if i >= 0)
    obj, _ = json.JSONDecoder().raw_decode(raw[start:])
    return obj


def main() -> int:
    # Confirm production branch still main
    proj = vercel_api(f"/v9/projects/{PROJECT_ID}?teamId={TEAM_ID}")
    assert isinstance(proj, dict)
    prod_branch = (proj.get("link") or {}).get("productionBranch")
    print(f"production_branch={prod_branch!r}")
    if prod_branch != "main":
        print("STOP: production branch is not main")
        return 2

    before = vercel_api(f"/v6/deployments?projectId={PROJECT_ID}&teamId={TEAM_ID}&limit=10")
    before_ids = {
        (d.get("uid") or d.get("id"))
        for d in ((before.get("deployments") if isinstance(before, dict) else before) or [])
    }

    # Local Preview deploy (includes uncommitted apps/web changes). NOT --prod.
    # Note: Deploy Hook cannot ship uncommitted work; CLI Preview is required.
    print("deploying_local_preview=yes (not Deploy Hook; uncommitted P3.7D.2)")
    proc = run(f"npx vercel deploy --yes --scope {SCOPE}")
    combined = (proc.stdout or "") + (proc.stderr or "")
    # Extract URLs without printing full log if huge
    urls = re.findall(r"https://[a-zA-Z0-9.-]+\.vercel\.app", combined)
    print(f"deploy_exit={proc.returncode}")
    print(f"urls_found={len(urls)}")
    for u in urls[-5:]:
        print(f"url={u}")
    if proc.returncode != 0:
        # Print last 800 chars sanitized
        print(combined[-800:].replace("token", "[redacted]"))
        return 3

    preview_url = urls[-1] if urls else None
    deadline = time.time() + 600
    while time.time() < deadline:
        deps = vercel_api(f"/v6/deployments?projectId={PROJECT_ID}&teamId={TEAM_ID}&limit=15")
        rows = deps.get("deployments") if isinstance(deps, dict) else deps
        for d in rows or []:
            did = d.get("uid") or d.get("id")
            if did in before_ids:
                continue
            target = d.get("target")
            state = d.get("readyState") or d.get("state")
            url = d.get("url")
            meta = d.get("meta") or {}
            branch = meta.get("githubCommitRef") or meta.get("gitBranch")
            sha = meta.get("githubCommitSha") or ""
            print(
                f"DEPLOY id={did} state={state} target={target!r} "
                f"branch={branch!r} sha={sha[:12] if sha else None} url=https://{url}"
            )
            if target == "production":
                print("CRITICAL: Production deployment — STOP")
                return 5
            if state in ("READY", "ERROR", "CANCELED"):
                print(f"FINAL state={state}")
                print(f"preview_url=https://{url}")
                print(f"deployment_id={did}")
                print(f"commit_sha={sha or 'local-uncommitted'}")
                print(f"cli_preview_url={preview_url}")
                return 0 if state == "READY" else 6
        time.sleep(10)

    print("TIMEOUT")
    return 7


if __name__ == "__main__":
    raise SystemExit(main())
