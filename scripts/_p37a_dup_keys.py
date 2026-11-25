"""Report duplicate .env keys and which value wins (last). Never print secrets."""
from pathlib import Path

env = Path(__file__).resolve().parents[1] / ".env"
seen: dict[str, list[tuple[int, bool]]] = {}
for i, line in enumerate(env.read_text(encoding="utf-8").splitlines(), 1):
    s = line.strip()
    if not s or s.startswith("#") or "=" not in s:
        continue
    k, v = s.split("=", 1)
    k = k.strip()
    seen.setdefault(k, []).append((i, bool(v.strip())))

dups = {k: locs for k, locs in seen.items() if len(locs) > 1}
print(f"duplicate_keys={len(dups)}")
for k, locs in sorted(dups.items()):
    last = locs[-1]
    print(f"{k}: occurrences={len(locs)} lines={[n for n,_ in locs]} last_filled={last[1]}")
