"""Inspect Vercel project via CLI API. No secrets printed."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ID = "prj_7TvXFLPGYq59spXXgEdjb0xkfr9c"
TEAM_ID = "team_5sXYYqiUCdvjfuzfdRK11yiS"
SCOPE = "kaushal-bhats-projects"


def vercel_api(path: str) -> object:
    cmd = [
        "npx",
        "vercel",
        "api",
        path,
        "--scope",
        SCOPE,
    ]
    proc = subprocess.run(
        cmd, cwd=ROOT, capture_output=True, text=True, check=False, shell=True
    )
    raw = (proc.stdout or "") + (proc.stderr or "")
    start = raw.find("{")
    if start < 0:
        start = raw.find("[")
    if start < 0:
        raise RuntimeError(f"no json in vercel api output status={proc.returncode}: {raw[:500]}")
    obj, _ = json.JSONDecoder().raw_decode(raw[start:])
    return obj


def main() -> int:
    data = vercel_api(f"/v9/projects/{PROJECT_ID}?teamId={TEAM_ID}")
    if not isinstance(data, dict):
        print("unexpected")
        return 1
    link = data.get("link") or {}
    print(f"id={data.get('id')}")
    print(f"name={data.get('name')}")
    print(f"framework={data.get('framework')}")
    print(f"rootDirectory={data.get('rootDirectory')}")
    print(f"nodeVersion={data.get('nodeVersion')}")
    print(f"buildCommand={data.get('buildCommand')}")
    print(f"installCommand={data.get('installCommand')}")
    print(f"outputDirectory={data.get('outputDirectory')}")
    print(f"link.type={link.get('type')}")
    print(f"link.org={link.get('org')}")
    print(f"link.repo={link.get('repo')}")
    print(f"link.productionBranch={link.get('productionBranch')}")
    print(f"link.deployHooks_count={len(link.get('deployHooks') or [])}")
    for h in link.get("deployHooks") or []:
        # Never print URL/token — names and refs only
        print(
            f"deployHook name={h.get('name')!r} ref={h.get('ref')!r} "
            f"id_present={bool(h.get('id'))} url_present={bool(h.get('url'))}"
        )

    envs = vercel_api(f"/v9/projects/{PROJECT_ID}/env?teamId={TEAM_ID}")
    items = envs.get("envs", envs) if isinstance(envs, dict) else envs
    if not isinstance(items, list):
        items = []
    print(f"env_count={len(items)}")
    for e in items:
        if not isinstance(e, dict):
            continue
        print(
            f"env key={e.get('key')} target={e.get('target')} "
            f"gitBranch={e.get('gitBranch')!r} type={e.get('type')} "
            f"id_present={bool(e.get('id'))}"
        )

    deps = vercel_api(
        f"/v6/deployments?projectId={PROJECT_ID}&teamId={TEAM_ID}&limit=5"
    )
    dep_list = deps.get("deployments", deps) if isinstance(deps, dict) else deps
    print(f"recent_deployments={len(dep_list) if isinstance(dep_list, list) else 0}")
    if isinstance(dep_list, list):
        for d in dep_list[:5]:
            print(
                f"dep id={d.get('uid') or d.get('id')} state={d.get('state') or d.get('readyState')} "
                f"target={d.get('target')} meta.gitBranch={((d.get('meta') or {}).get('githubCommitRef') or (d.get('meta') or {}).get('gitBranch'))!r} "
                f"url={d.get('url')}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
