"""Stage release/p3-7b-staging files by allowlist. Never stages .env."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXCLUDE_PREFIXES = (
    ".env",
    ".venv/",
    "node_modules/",
    ".playwright-mcp/",
    "apps/web/playwright-report/",
    "apps/web/test-results/",
    "__pycache__/",
    ".mypy_cache/",
    ".ruff_cache/",
    "scripts/_p37a_",
    "scripts/_p37b_",
    "scripts/_p37b_selected_service_id.txt",
)

# Paths / prefixes to include from working tree
INCLUDE_PREFIXES = (
    "backend/",
    "tests/",
    "apps/web/",
    "packages/ui/",
    "docs/deployment/",
    "docs/security/",
    "docs/pilot-readiness/",
    "docs/commercial/",
    "docs/product/",
    ".env.example",
    "DESIGN.md",
    "package-lock.json",
    "packages/ui/package.json",
    "apps/web/package.json",
    "apps/web/next.config.mjs",
)


def status_paths() -> list[str]:
    out = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
    paths: list[str] = []
    for line in out.splitlines():
        if len(line) < 4:
            continue
        # porcelain: XY PATH or XY ORIG -> PATH
        rest = line[3:]
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]
        paths.append(rest.strip().strip('"'))
    return paths


def allowed(path: str) -> bool:
    norm = path.replace("\\", "/")
    if norm == ".env" or norm.startswith(".env."):
        # allow only .env.example
        if norm != ".env.example":
            return False
    for p in EXCLUDE_PREFIXES:
        if norm == p.rstrip("/") or norm.startswith(p):
            return False
    if "/__pycache__/" in f"/{norm}/" or norm.endswith(".pyc"):
        return False
    for p in INCLUDE_PREFIXES:
        if norm == p.rstrip("/") or norm.startswith(p):
            return True
    return False


def main() -> int:
    paths = [p for p in status_paths() if allowed(p)]
    # Always ensure security test file exists
    extra = [
        "tests/security/test_p36_document_consent_isolation.py",
    ]
    for e in extra:
        if (ROOT / e).exists() and e not in paths:
            paths.append(e)
    paths = sorted(set(paths))
    print(f"staging_count={len(paths)}")
    if not paths:
        print("NO_PATHS")
        return 1
    # write manifest
    man = ROOT / "docs" / "deployment" / "P3-7B-release-manifest.md"
    man.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# P3.7B Release Manifest\n",
        "\n",
        f"**Branch:** `release/p3-7b-staging`  \n",
        f"**Base:** `2a0974e41af9e334e147794f45e258f34d6814d3`  \n",
        f"**File count:** {len(paths)}\n",
        "\n",
        "## Included paths\n",
        "\n",
    ]
    for p in paths:
        reason = "backend/runtime"
        if p.startswith("tests/"):
            reason = "regression/security tests"
        elif p.startswith("docs/"):
            reason = "release evidence/docs"
        elif p.startswith("apps/web/") or p.startswith("packages/ui/"):
            reason = "web/UI companion for API surfaces"
        elif p.endswith("0018") or "alembic/versions" in p:
            reason = "schema migration (0018–0027 chain)"
        lines.append(f"- `{p}` — {reason}\n")
    lines.append("\n## Explicitly excluded\n\n")
    lines.append("- `.env` and all secrets\n")
    lines.append("- `scripts/_p37a_*` / `scripts/_p37b_*` local ops helpers\n")
    lines.append("- Playwright reports, caches, venvs, node_modules\n")
    man.write_text("".join(lines), encoding="utf-8")
    if str(man.relative_to(ROOT)).replace("\\", "/") not in paths:
        paths.append(str(man.relative_to(ROOT)).replace("\\", "/"))

    # stage in batches
    for i in range(0, len(paths), 40):
        batch = paths[i : i + 40]
        subprocess.check_call(["git", "add", "--", *batch], cwd=ROOT)
    print("STAGED_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
