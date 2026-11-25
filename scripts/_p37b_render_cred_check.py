"""Check for Render credentials without printing values."""
from __future__ import annotations

import os
from pathlib import Path

env: dict[str, str] = {}
for line in Path(".env").read_text(encoding="utf-8").splitlines():
    s = line.strip()
    if not s or s.startswith("#") or "=" not in s:
        continue
    k, v = s.split("=", 1)
    env[k.strip()] = v.strip()

keys = [
    "RENDER_API_KEY",
    "RENDER_API_TOKEN",
    "RENDER_TOKEN",
    "RENDER_OWNER_ID",
    "RENDER_SERVICE_ID",
]
for k in keys:
    if k in env:
        print(f"{k}: {'PRESENT_FILLED' if env[k] else 'PRESENT_EMPTY'}")
    else:
        print(f"{k}: MISSING_KEY")
    print(f"process_{k}: {'SET' if os.environ.get(k) else 'UNSET'}")

# JWT cloud
print(f"JWT_SECRET_CLOUD: {'PRESENT_FILLED' if env.get('JWT_SECRET_CLOUD') else 'PRESENT_EMPTY'}")
print(f"ALLOWED_ORIGINS_CLOUD: {'PRESENT_FILLED' if env.get('ALLOWED_ORIGINS_CLOUD') else 'PRESENT_EMPTY'}")
print(f"API_PUBLIC_URL_CLOUD: {'PRESENT_FILLED' if env.get('API_PUBLIC_URL_CLOUD') else 'PRESENT_EMPTY'}")
