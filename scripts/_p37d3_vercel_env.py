"""Configure Preview env for same-origin proxy. Never prints values."""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCOPE = "kaushal-bhats-projects"
UPSTREAM = "https://micronest-medicalos.onrender.com"


def run(cmd: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=ROOT,
        input=input_text,
        capture_output=True,
        text=True,
        shell=True,
        check=False,
    )


def main() -> int:
    # 1) Add/override server-only rewrite upstream for Preview (branch-scoped)
    add = (
        f"npx vercel env add API_REWRITE_UPSTREAM preview release/p3-7b-staging "
        f"--scope {SCOPE} --force --yes"
    )
    proc = run(add, input_text=UPSTREAM + "\n")
    out = ((proc.stdout or "") + (proc.stderr or "")).replace(UPSTREAM, "[UPSTREAM]")
    print(out[-1500:])
    print(f"add_rewrite_exit={proc.returncode}")

    # Also add Preview-wide (no branch) so CLI Preview deploys without git branch meta still work
    add2 = f"npx vercel env add API_REWRITE_UPSTREAM preview --scope {SCOPE} --force --yes"
    proc2 = run(add2, input_text=UPSTREAM + "\n")
    out2 = ((proc2.stdout or "") + (proc2.stderr or "")).replace(UPSTREAM, "[UPSTREAM]")
    print(out2[-1200:])
    print(f"add_rewrite_preview_wide_exit={proc2.returncode}")

    # 2) Remove obsolete NEXT_PUBLIC_API_URL from Preview (branch-scoped)
    # Interactive confirm — use --yes if supported
    rm = (
        f"npx vercel env rm NEXT_PUBLIC_API_URL preview release/p3-7b-staging "
        f"--scope {SCOPE} --yes"
    )
    proc3 = run(rm)
    print(((proc3.stdout or "") + (proc3.stderr or ""))[-1200:])
    print(f"rm_next_public_exit={proc3.returncode}")

    # List names/scopes only
    ls = run(f"npx vercel env ls --scope {SCOPE}")
    print((ls.stdout or ls.stderr or "")[-2500:])
    return 0 if proc.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
