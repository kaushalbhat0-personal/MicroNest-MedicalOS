"""Scan Alembic migrations for readiness notes. No secrets."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERS = ROOT / "backend" / "alembic" / "versions"


def main() -> None:
    files = sorted(VERS.glob("*.py"))
    print(f"migration_files={len(files)}")
    chain: list[tuple[str, str | None]] = []
    flags = {
        "create_role": [],
        "drop_": [],
        "extension": [],
        "force_rls": [],
        "grant_hos_app": [],
        "raw_execute": 0,
    }
    for f in files:
        text = f.read_text(encoding="utf-8")
        rev_m = re.search(r'^revision:\s*str\s*=\s*[\'"]([^\'"]+)', text, re.M)
        down_m = re.search(
            r'^down_revision:\s*str\s*\|\s*Sequence\[str\]\s*\|\s*None\s*=\s*[\'"]?([^\'"\n]+)',
            text,
            re.M,
        )
        rev = rev_m.group(1) if rev_m else f.stem
        down = None
        if down_m:
            raw = down_m.group(1).strip()
            if raw not in ("None", "none"):
                down = raw.strip("'\"")
        chain.append((rev, down))
        if "CREATE ROLE" in text or "create role" in text.lower():
            flags["create_role"].append(rev)
        if re.search(r"\bDROP\b", text):
            flags["drop_"].append(rev)
        if "CREATE EXTENSION" in text.upper():
            flags["extension"].append(rev)
        if "FORCE ROW LEVEL SECURITY" in text:
            flags["force_rls"].append(rev)
        if "hos_app" in text and "GRANT" in text:
            flags["grant_hos_app"].append(rev)
        flags["raw_execute"] += text.count("op.execute")

    print("=== revision chain (rev <- down) ===")
    by_down = {d: r for r, d in chain}
    # find root
    roots = [r for r, d in chain if d is None]
    print(f"roots={roots}")
    # walk
    order = []
    cur = roots[0] if roots else None
    seen = set()
    while cur and cur not in seen:
        order.append(cur)
        seen.add(cur)
        # find next whose down is cur
        nxt = [r for r, d in chain if d == cur]
        cur = nxt[0] if nxt else None
    print(f"ordered_count={len(order)} head={order[-1] if order else None}")
    print(f"create_role_revs={flags['create_role']}")
    print(f"extension_revs={flags['extension']}")
    print(f"force_rls_revs={flags['force_rls']}")
    print(f"grant_hos_app_rev_count={len(flags['grant_hos_app'])}")
    print(f"revisions_with_DROP_keyword={flags['drop_']}")
    print(f"op.execute_calls≈{flags['raw_execute']}")
    if order and order[-1].startswith("0027"):
        print("HEAD_EXPECTED=0027_saas_payment_reliability OK")
    else:
        print(f"HEAD_ACTUAL={order[-1] if order else None}")


if __name__ == "__main__":
    main()
