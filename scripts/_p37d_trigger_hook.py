"""Trigger staging Deploy Hook without printing URL/token. Monitor until READY/ERROR."""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCOPE = "kaushal-bhats-projects"
PROJECT_ID = "prj_7TvXFLPGYq59spXXgEdjb0xkfr9c"
TEAM_ID = "team_5sXYYqiUCdvjfuzfdRK11yiS"
HOOK_NAME = "healthcare-os-staging"
EXPECTED_BRANCH = "release/p3-7b-staging"
EXPECTED_SHA = "293dc668e7117f20a4b88e7a3047aa8e501c99b6"


def vercel_api(path: str) -> dict | list:
    proc = subprocess.run(
        f"npx vercel api {path} --scope {SCOPE}",
        cwd=ROOT,
        capture_output=True,
        text=True,
        shell=True,
        check=False,
    )
    raw = (proc.stdout or "").strip()
    # Find JSON start even if CLI prepends noise
    idx = raw.find("{")
    idx2 = raw.find("[")
    cands = [i for i in (idx, idx2) if i >= 0]
    if not cands:
        raise RuntimeError(f"no json in api response for {path}: {(proc.stderr or raw)[:400]}")
    start = min(cands)
    obj, _ = json.JSONDecoder().raw_decode(raw[start:])
    return obj  # type: ignore[return-value]


def post_hook(url: str) -> dict:
    req = urllib.request.Request(url, method="POST", data=b"", headers={"User-Agent": "p37d-deploy"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return {"status": resp.status, "body": json.loads(body) if body.strip().startswith("{") else body}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"status": e.code, "body": body}


def main() -> int:
    projects = vercel_api(f"/v9/projects/{PROJECT_ID}?teamId={TEAM_ID}")
    assert isinstance(projects, dict)
    pid = projects.get("id")
    print(f"project_id={pid}")
    print(f"production_branch={projects.get('link', {}).get('productionBranch')}")
    print(f"rootDirectory={projects.get('rootDirectory')}")

    items = (projects.get("link") or {}).get("deployHooks") or []
    target = None
    for h in items:
        name = h.get("name") or ""
        ref = h.get("ref") or ""
        print(f"hook_found name={name!r} ref={ref!r} url_present={bool(h.get('url'))}")
        if name == HOOK_NAME and ref == EXPECTED_BRANCH:
            target = h
            break

    if not target:
        print("ERROR: deploy hook not found via API; abort without trigger")
        return 2

    url = target.get("url") or target.get("hookUrl")
    if not url:
        print("ERROR: hook has no URL field in API response; ask user to trigger manually")
        return 3

    ref = target.get("ref") or ""
    print(f"triggering_hook name={target.get('name')!r} ref={ref!r} (url redacted)")

    # Snapshot existing deployment IDs so we only track the new one
    before = vercel_api(f"/v6/deployments?projectId={PROJECT_ID}&teamId={TEAM_ID}&limit=20")
    before_ids = {
        (d.get("uid") or d.get("id"))
        for d in ((before.get("deployments") if isinstance(before, dict) else before) or [])
    }

    result = post_hook(url)
    status = result.get("status")
    body = result.get("body")
    if isinstance(body, dict):
        print(f"hook_http={status} job_keys={list(body.keys())}")
    else:
        print(f"hook_http={status} body_type={type(body).__name__}")

    print("polling deployments...")
    deadline = time.time() + 900
    tracked: str | None = None
    while time.time() < deadline:
        deps = vercel_api(f"/v6/deployments?projectId={PROJECT_ID}&teamId={TEAM_ID}&limit=15")
        rows = deps.get("deployments") if isinstance(deps, dict) else deps
        for d in rows or []:
            did = d.get("uid") or d.get("id")
            meta = d.get("meta") or {}
            branch = meta.get("githubCommitRef") or meta.get("gitBranch")
            sha = meta.get("githubCommitSha") or ""
            target_env = d.get("target")
            state = d.get("readyState") or d.get("state")
            url_host = d.get("url")
            is_new = did not in before_ids
            is_staging = branch == EXPECTED_BRANCH or (sha.startswith(EXPECTED_SHA[:12]) if sha else False)
            if not (is_new and is_staging):
                continue
            tracked = did
            print(
                f"DEPLOY id={did} state={state} target={target_env!r} "
                f"branch={branch} sha={sha[:12] if sha else None} url=https://{url_host}"
            )
            if target_env == "production":
                print("CRITICAL: Production deployment detected from staging hook — STOP")
                return 5
            if state in ("READY", "ERROR", "CANCELED"):
                print(f"FINAL state={state}")
                print(f"preview_url=https://{url_host}")
                print(f"deployment_id={did}")
                print(f"commit_sha={sha}")
                print(f"matches_expected_sha={sha == EXPECTED_SHA}")
                return 0 if state == "READY" else 6
        if tracked is None:
            print("waiting_for_new_staging_deployment...")
        time.sleep(15)

    print("TIMEOUT waiting for deployment")
    return 7


if __name__ == "__main__":
    raise SystemExit(main())
