"""Check whether Preview bundle embeds Render API URL (never print secrets)."""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = "https://micro-nest-medical-8eeq5wwe6-kaushal-bhats-projects.vercel.app"
sec = json.loads((ROOT / ".vercel" / "p37d_protection_bypass.json").read_text(encoding="utf-8"))["secret"]


def fetch(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"x-vercel-protection-bypass": sec, "User-Agent": "p37d-check"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
        return resp.read()


def main() -> int:
    html = fetch(f"{PREVIEW}/login?x-vercel-protection-bypass={sec}").decode("utf-8", "replace")
    print(f"html_len={len(html)}")
    print(f"html_has_onrender={'micronest-medicalos.onrender.com' in html}")
    print(f"html_has_localhost8000={'localhost:8000' in html}")
    srcs = re.findall(r'src="(/_next/static/[^"]+)"', html)
    print(f"script_count={len(srcs)}")
    cloud = 0
    local = 0
    for s in srcs[:12]:
        try:
            body = fetch(f"{PREVIEW}{s}?x-vercel-protection-bypass={sec}")
        except Exception as exc:  # noqa: BLE001
            print(f"chunk_err {s}: {type(exc).__name__}")
            continue
        if b"micronest-medicalos.onrender.com" in body:
            cloud += 1
        if b"localhost:8000" in body or b"127.0.0.1:8000" in body:
            local += 1
    print(f"chunks_with_onrender={cloud}")
    print(f"chunks_with_localhost={local}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
