"""Add Preview-only NEXT_PUBLIC_API_URL via Vercel CLI. Never prints secrets."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCOPE = "kaushal-bhats-projects"
API = "https://micronest-medicalos.onrender.com"


def run(cmd: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
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
    # Branch-scoped Preview env for release/p3-7b-staging only
    cmd = (
        f'npx vercel env add NEXT_PUBLIC_API_URL preview release/p3-7b-staging '
        f'--scope {SCOPE} --force --yes'
    )
    proc = run(cmd, input_text=API + "\n")
    out = (proc.stdout or "") + (proc.stderr or "")
    # Redact any accidental echo of value
    safe = out.replace(API, "[API_URL]")
    print(safe[-2000:])
    print(f"exit={proc.returncode}")

    # Optional: HSTS gate for HTTPS preview (not a secret)
    cmd2 = (
        f'npx vercel env add COOKIE_SECURE preview release/p3-7b-staging '
        f'--scope {SCOPE} --force --yes'
    )
    proc2 = run(cmd2, input_text="true\n")
    out2 = (proc2.stdout or "") + (proc2.stderr or "")
    print(out2[-1500:])
    print(f"cookie_secure_exit={proc2.returncode}")

    # List env names only
    ls = run(f"npx vercel env ls --scope {SCOPE}")
    print((ls.stdout or ls.stderr or "")[-2500:])
    return 0 if proc.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
