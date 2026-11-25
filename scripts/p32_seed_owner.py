"""P3.2 synthetic owner seed for authenticated Playwright (local/dev only).

Creates or updates a password-backed owner user from env. Does not create a
tenant — the owner journey creates the workspace via the UI/API.

Env (required):
  OWNER_DATABASE_URL
  PLAYWRIGHT_OWNER_EMAIL
  PLAYWRIGHT_OWNER_PASSWORD

Optional:
  PLAYWRIGHT_OWNER_NAME (default: P32 Synthetic Owner)

Refuses to run when ENV is preview/prod/production.
Never prints the password.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

# Load root .env if present (pydantic settings also reads it for the API).
_env_path = ROOT / ".env"
if _env_path.is_file():
    for line in _env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def main() -> int:
    env = (os.environ.get("ENV") or "dev").lower()
    if env in ("preview", "prod", "production"):
        print("REFUSED: p32_seed_owner is for local/dev/test only", file=sys.stderr)
        return 2

    email = os.environ.get("PLAYWRIGHT_OWNER_EMAIL", "").strip()
    password = os.environ.get("PLAYWRIGHT_OWNER_PASSWORD", "").strip()
    name = os.environ.get("PLAYWRIGHT_OWNER_NAME", "P32 Synthetic Owner").strip()
    owner_url = os.environ.get("OWNER_DATABASE_URL", "").strip()

    missing = [
        k
        for k, v in [
            ("PLAYWRIGHT_OWNER_EMAIL", email),
            ("PLAYWRIGHT_OWNER_PASSWORD", password),
            ("OWNER_DATABASE_URL", owner_url),
        ]
        if not v
    ]
    if missing:
        print(f"BLOCKED: missing env: {', '.join(missing)}", file=sys.stderr)
        return 2

    if len(password) < 12:
        print("BLOCKED: PLAYWRIGHT_OWNER_PASSWORD must be at least 12 chars", file=sys.stderr)
        return 2

    from app.modules.identity import service as identity_service
    from app.platform import db as dbmod

    factory = dbmod.make_session_factory(owner_url)
    with factory() as db:
        user = identity_service.get_user_by_email(db, email)
        if user is None:
            user = identity_service.create_user(
                db, email=email, display_name=name, password=password
            )
            action = "created"
        else:
            identity_service.set_password(db, user, password)
            if name and user.display_name != name:
                user.display_name = name
            action = "updated"
        db.commit()
        print(f"synthetic_owner={action} email={user.email} id={user.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
