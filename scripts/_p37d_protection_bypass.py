"""Generate Vercel automation protection bypass (never print secret). Persist to gitignored local file."""
from __future__ import annotations

import json
import secrets
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCOPE = "kaushal-bhats-projects"
PROJECT_ID = "prj_7TvXFLPGYq59spXXgEdjb0xkfr9c"
TEAM_ID = "team_5sXYYqiUCdvjfuzfdRK11yiS"
OUT = ROOT / ".vercel" / "p37d_protection_bypass.json"


def vercel_api(path: str, *, method: str = "GET", body: dict | None = None) -> object:
    cmd = f'npx vercel api {path} --scope {SCOPE}'
    if method != "GET":
        cmd += f" --method {method}"
    input_text = None
    if body is not None:
        tmp = ROOT / ".vercel" / "_p37d_bypass_body.json"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(body), encoding="utf-8")
        cmd += f' --input "{tmp}"'
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, shell=True, check=False)
    raw = (proc.stdout or "") + (proc.stderr or "")
    start = min(i for i in (raw.find("{"), raw.find("[")) if i >= 0)
    obj, _ = json.JSONDecoder().raw_decode(raw[start:])
    return obj


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # Prefer existing local secret if present
    if OUT.exists():
        data = json.loads(OUT.read_text(encoding="utf-8"))
        if data.get("secret") and len(data["secret"]) >= 32:
            print("bypass_secret_exists_locally=True")
            print(f"path={OUT.as_posix()}")
            return 0

    secret = secrets.token_hex(16)  # 32 hex chars
    assert len(secret) == 32
    # PATCH /v1/projects/:id/protection-bypass
    body = {
        "generate": {
            "secret": secret,
            "note": "P3.7D staging preview automation",
        }
    }
    try:
        result = vercel_api(
            f"/v1/projects/{PROJECT_ID}/protection-bypass?teamId={TEAM_ID}",
            method="PATCH",
            body=body,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"API_PATCH_failed={type(exc).__name__}")
        # Fallback: empty generate (random)
        body = {"generate": {"note": "P3.7D staging preview automation"}}
        result = vercel_api(
            f"/v1/projects/{PROJECT_ID}/protection-bypass?teamId={TEAM_ID}",
            method="PATCH",
            body=body,
        )
        # Response may contain the generated secret once
        if isinstance(result, dict):
            for k, v in result.items():
                if isinstance(v, dict) and v.get("createdAt"):
                    secret = k
                    break
                if k and len(k) == 32 and k.isalnum():
                    secret = k
                    break

    OUT.write_text(
        json.dumps(
            {
                "secret": secret,
                "note": "P3.7D staging preview automation — DO NOT COMMIT",
                "header": "x-vercel-protection-bypass",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    # Ensure gitignored
    gi = ROOT / ".vercel" / ".gitignore"
    if not gi.exists():
        gi.write_text("*\n", encoding="utf-8")
    print("bypass_secret_written=True")
    print(f"path={OUT.as_posix()}")
    print(f"secret_len={len(secret)}")
    print("secret_value=REDACTED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
