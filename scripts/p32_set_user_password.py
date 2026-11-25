"""P3.2 test helper: set a user's password (local/dev only).

Used after portal enrollment so Playwright can log in as the synthetic
patient without scraping DEV notification logs for reset tokens.

Env: OWNER_DATABASE_URL
Args: --email --password
Refuses preview/prod/production.
Never prints the password.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

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
        print("REFUSED: p32_set_user_password is for local/dev/test only", file=sys.stderr)
        return 2

    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()
    if len(args.password) < 12:
        print("BLOCKED: password must be at least 12 chars", file=sys.stderr)
        return 2

    owner_url = os.environ.get("OWNER_DATABASE_URL", "").strip()
    if not owner_url:
        print("BLOCKED: OWNER_DATABASE_URL missing", file=sys.stderr)
        return 2

    from app.modules.identity import service as identity_service
    from app.platform import db as dbmod

    factory = dbmod.make_session_factory(owner_url)
    with factory() as db:
        user = identity_service.get_user_by_email(db, args.email)
        if user is None:
            print(f"BLOCKED: user not found for email={args.email}", file=sys.stderr)
            return 2
        identity_service.set_password(db, user, args.password)
        db.commit()
        print(f"password_set email={user.email} id={user.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
