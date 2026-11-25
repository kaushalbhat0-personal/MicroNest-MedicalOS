"""Rewrite OWNER/APP cloud URLs to session-pooler hos_* roles. Never print secrets."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote, urlparse

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"


def load_env_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines(keepends=True)


def parse_env(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def main() -> None:
    raw = ENV_PATH.read_text(encoding="utf-8")
    env = parse_env(raw)
    ref = env["SUPABASE_PROJECT_REF"]
    pw = quote(env["APP_ROLE_PASSWORD_CLOUD"], safe="")
    owner_src = env["OWNER_DATABASE_URL_CLOUD"].replace(
        "postgresql+psycopg2://", "postgresql://", 1
    )
    host = urlparse(owner_src).hostname
    port = urlparse(owner_src).port or 5432
    owner_url = (
        f"postgresql+psycopg2://hos_owner.{ref}:{pw}@{host}:{port}/postgres?sslmode=require"
    )
    app_url = (
        f"postgresql+psycopg2://hos_app.{ref}:{pw}@{host}:{port}/postgres?sslmode=require"
    )

    lines = load_env_lines(ENV_PATH)
    out: list[str] = []
    for line in lines:
        if line.startswith("OWNER_DATABASE_URL_CLOUD="):
            out.append(f"OWNER_DATABASE_URL_CLOUD={owner_url}\n")
        elif line.startswith("APP_DATABASE_URL_CLOUD="):
            out.append(f"APP_DATABASE_URL_CLOUD={app_url}\n")
        else:
            out.append(line if line.endswith("\n") else line + "\n")
    ENV_PATH.write_text("".join(out), encoding="utf-8")
    print("rewrote OWNER_DATABASE_URL_CLOUD -> hos_owner.<ref>@session-pooler")
    print("rewrote APP_DATABASE_URL_CLOUD -> hos_app.<ref>@session-pooler")
    print(f"host={host} port={port} sslmode=require")


if __name__ == "__main__":
    main()
