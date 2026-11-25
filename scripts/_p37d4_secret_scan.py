"""Scan proposed P3.7D.4 release files for secret-like content. No values printed."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEEDLES = [
    "RENDER_API_KEY=",
    "deploy.webhook",
    "/v1/integrations/deploy",
    "x-vercel-protection-bypass",
    "P37C_OWNER_A_PASSWORD",
    "postgresql://",
    "postgres://",
    "sbp_",
    "eyJhbGci",
]

PROPOSED = [
    "apps/web/next.config.mjs",
    "apps/web/lib/api.ts",
    "apps/web/lib/apiBase.ts",
    "apps/web/lib/apiBase.test.ts",
    "apps/web/lib/apiProxyConfig.mjs",
    "apps/web/lib/apiProxyConfig.test.ts",
    ".env.example",
    ".vercelignore",
    "docs/security/P3-7D1-same-origin-auth-architecture-audit.md",
    "docs/security/P3-7D2-same-origin-proxy-implementation.md",
    "docs/deployment/P3-7D3-same-origin-preview-verification.md",
    "backend/app/platform/security/cookies.py",
]


def main() -> int:
    bad = 0
    for rel in PROPOSED:
        p = ROOT / rel
        if not p.exists():
            print(f"MISSING {rel}")
            bad += 1
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        hits = [n for n in NEEDLES if n.lower() in text.lower()]
        print(f"{rel}: {'HITS ' + ','.join(hits) if hits else 'clean'}")
        if hits:
            bad += 1

    # evidence / local-only must stay out
    exclude = [
        "scripts/_p37d3_verify_results.json",
        "scripts/_p37d_smoke_results.json",
        "apps/web/playwright-report",
        "apps/web/test-results",
        ".playwright-mcp",
        ".vercel",
        ".env.p37c.staging",
        ".env.local",
    ]
    for rel in exclude:
        p = ROOT / rel
        print(f"EXCLUDE_FROM_RELEASE exists={p.exists()} path={rel}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
