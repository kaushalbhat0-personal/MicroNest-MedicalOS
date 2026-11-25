"""Generate P3.7C synthetic credentials into a gitignored local artifact.

Writes `.env.p37c.staging` (matched by `.env.*` in .gitignore).
Never prints password values.

Note: EmailStr/email-validator rejects reserved special-use domains such as
`.test`. Synthetic addresses use `@example.com` (RFC 2606) instead.
"""
from __future__ import annotations

import argparse
import secrets
import string
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".env.p37c.staging"


def strong_password(n: int = 24) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(n))
        if (
            any(c.islower() for c in pw)
            and any(c.isupper() for c in pw)
            and any(c.isdigit() for c in pw)
            and any(c in "!@#$%^&*-_" for c in pw)
            and len(pw) >= 12
        ):
            return pw


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Overwrite existing artifact")
    args = parser.parse_args()
    if OUT.exists() and not args.force:
        print(f"EXISTS {OUT.name} — leaving unchanged (use --force to regenerate)")
        return 0
    # Unique per generation so re-runs don't collide with prior signup rows
    # (duplicate signup returns opaque 202 and does not reset the password).
    tag = secrets.token_hex(3)
    rows = {
        "P37C_API_BASE": "https://micronest-medicalos.onrender.com",
        "P37C_RUN_TAG": tag,
        "P37C_OWNER_A_EMAIL": f"p37c.owner.alpha.{tag}@example.com",
        "P37C_OWNER_A_PASSWORD": strong_password(),
        "P37C_OWNER_A_NAME": "Synthetic Owner Alpha",
        "P37C_OWNER_B_EMAIL": f"p37c.owner.beta.{tag}@example.com",
        "P37C_OWNER_B_PASSWORD": strong_password(),
        "P37C_OWNER_B_NAME": "Synthetic Owner Beta",
        "P37C_RECV_A_EMAIL": f"p37c.recv.alpha.{tag}@example.com",
        "P37C_RECV_A_PASSWORD": strong_password(),
        "P37C_RECV_A_NAME": "Synthetic Receptionist Alpha",
        "P37C_PORTAL_A1_EMAIL": f"p37c.portal.a1.{tag}@example.com",
        "P37C_PORTAL_A1_PASSWORD": strong_password(),
        "P37C_PORTAL_A1_NAME": "Synthetic Portal Patient A1",
        "P37C_PORTAL_A2_EMAIL": f"p37c.portal.a2.{tag}@example.com",
        "P37C_PORTAL_A2_PASSWORD": strong_password(),
        "P37C_PORTAL_A2_NAME": "Synthetic Portal Patient A2",
        "P37C_CLINIC_A_NAME": "Synthetic Clinic Alpha",
        "P37C_CLINIC_A_SLUG": f"synth-clinic-alpha-{tag}",
        "P37C_CLINIC_B_NAME": "Synthetic Clinic Beta",
        "P37C_CLINIC_B_SLUG": f"synth-clinic-beta-{tag}",
        "P37C_EMAIL_DOMAIN_NOTE": (
            "example.com used because EmailStr rejects reserved .test domains"
        ),
    }
    lines = ["# P3.7C synthetic staging credentials — DO NOT COMMIT", ""]
    lines += [f"{k}={v}" for k, v in rows.items()]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"WROTE {OUT.name}")
    print(
        "non_secret_emails="
        + ",".join(v for k, v in rows.items() if k.endswith("_EMAIL"))
    )
    print(f"password_keys_written={sum(1 for k in rows if 'PASSWORD' in k)} (values not printed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
