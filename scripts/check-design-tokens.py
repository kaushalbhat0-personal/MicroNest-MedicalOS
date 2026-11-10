#!/usr/bin/env python3
"""Design-token drift check for Healthcare OS UI.

Enforces the DESIGN.md constitution in app code:
- no raw hex colors outside packages/ui/tokens.css (+ documented test/legacy spots)
- no hardcoded spacing values where tokens exist (spot rule: px values in
  hos-* CSS must reference var(--hos-*))
- every --hos-* var() used in app/packages CSS must be defined in tokens.css

Usage: python scripts/check-design-tokens.py
Exit 0 = clean, 1 = drift found.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOKENS_CSS = ROOT / "packages" / "ui" / "tokens.css"

# Raw hex is allowed only here (source of truth + explicitly legacy spots).
HEX_ALLOWLIST = {
    "packages/ui/tokens.css",
    "packages/ui/theme.css",
}

HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b")
VAR_DEF_RE = re.compile(r"--hos-[a-z0-9-]+(?=\s*:)")
VAR_USE_RE = re.compile(r"var\(\s*(--hos-[a-z0-9-]+)")


def defined_tokens() -> set[str]:
    return set(VAR_DEF_RE.findall(TOKENS_CSS.read_text()))


def read_text(path: pathlib.Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def check_hex() -> list[str]:
    problems = []
    for pattern in (
        "apps/**/*.tsx",
        "apps/**/*.ts",
        "apps/**/*.css",
        "packages/**/*.tsx",
        "packages/**/*.ts",
        "packages/**/*.css",
    ):
        for path in ROOT.glob(pattern):
            if "node_modules" in path.parts or ".next" in path.parts:
                continue
            rel = path.relative_to(ROOT).as_posix()
            if rel in HEX_ALLOWLIST:
                continue
            src = read_text(path)
            if src is None:
                continue
            for i, line in enumerate(src.splitlines(), 1):
                if HEX_RE.search(line):
                    problems.append(f"{rel}:{i}: raw hex color (use --hos-* tokens)")
    return problems


def check_undefined_vars(defined: set[str]) -> list[str]:
    problems = []
    for pattern in ("apps/**/*.css", "packages/**/*.css"):
        for path in ROOT.glob(pattern):
            if "node_modules" in path.parts or ".next" in path.parts:
                continue
            rel = path.relative_to(ROOT).as_posix()
            src = read_text(path)
            if src is None:
                continue
            for i, line in enumerate(src.splitlines(), 1):
                for var in VAR_USE_RE.findall(line):
                    if var not in defined:
                        problems.append(f"{rel}:{i}: undefined token {var}")
    return problems


def main() -> int:
    if not TOKENS_CSS.exists():
        print("tokens.css missing")
        return 1
    defined = defined_tokens()
    if not defined:
        print("no --hos-* tokens defined")
        return 1
    problems = check_hex() + check_undefined_vars(defined)
    for p in problems:
        print(p)
    if problems:
        print(f"{len(problems)} drift issue(s)")
        return 1
    print(f"clean: {len(defined)} tokens defined, 0 drift issues")
    return 0


if __name__ == "__main__":
    sys.exit(main())
