"""P3.7A: print .env key names and filled/empty only. Never print values."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"

INTEREST = (
    "SUPABASE",
    "S3_",
    "STORAGE",
    "_CLOUD",
    "RENDER",
    "VERCEL",
    "OWNER_DATABASE",
    "APP_DATABASE",
    "JWT_SECRET",
    "DEPLOYMENT",
    "API_PUBLIC",
    "ALLOWED_ORIGINS",
    "NEXT_PUBLIC",
    "DB_SSL",
    "COOKIE",
    "NOTIFY",
)


def load_pairs(path: Path) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        pairs.append((k.strip(), v.strip()))
    return pairs


def redact_url_shape(url: str) -> str:
    """Describe URL shape without credentials or host secrets beyond host class."""
    if not url:
        return "EMPTY"
    try:
        # sqlalchemy URLs may use postgresql+psycopg2://
        raw = url.replace("postgresql+psycopg2://", "postgresql://", 1)
        u = urlparse(raw)
        user = u.username or ""
        host = u.hostname or ""
        port = u.port
        db = (u.path or "").lstrip("/")
        ssl = "sslmode=" in (u.query or "")
        host_class = "unknown"
        hl = host.lower()
        if "supabase" in hl:
            if "pooler" in hl:
                host_class = "supabase-pooler"
            elif hl.startswith("db."):
                host_class = "supabase-direct"
            else:
                host_class = "supabase-other"
        elif hl in ("localhost", "127.0.0.1"):
            host_class = "local"
        role_hint = user if user in ("hos_owner", "hos_app", "postgres", "authenticator") else (
            "custom-user" if user else "no-user"
        )
        return (
            f"SET scheme={u.scheme or '?'} user={role_hint} "
            f"host_class={host_class} port={port} db={db or '?'} sslmode={ssl}"
        )
    except Exception as exc:  # noqa: BLE001
        return f"SET unparseable ({type(exc).__name__})"


def classify_token(name: str, value: str) -> str:
    if not value:
        return "EMPTY"
    if name in ("S3_ACCESS_KEY", "S3_SECRET_KEY", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"):
        # Heuristic only: never print value. Supabase S3 keys often look like opaque strings.
        if value.startswith("sb_secret_") or value.startswith("sbp_"):
            return "SET kind=likely-supabase-management-or-secret-api-key"
        if value.startswith("eyJ"):
            return "SET kind=likely-jwt"
        return "SET kind=opaque-credential"
    if "TOKEN" in name or "ACCESS_TOKEN" in name:
        if value.startswith("sbp_"):
            return "SET kind=likely-supabase-personal-access-token"
        if value.startswith("eyJ"):
            return "SET kind=likely-jwt"
        return "SET kind=opaque-token"
    return "SET"


def main() -> None:
    pairs = load_pairs(ENV)
    print(f"env_file={ENV.name} key_count={len(pairs)}")
    print("--- interest keys ---")
    for k, v in pairs:
        if not any(x in k for x in INTEREST):
            continue
        if "DATABASE_URL" in k or k.endswith("_URL") and "S3" not in k and "API" in k:
            print(f"{k}: {redact_url_shape(v)}")
        elif "DATABASE_URL" in k:
            print(f"{k}: {redact_url_shape(v)}")
        elif k in (
            "S3_ENDPOINT_URL",
            "S3_ENDPOINT",
            "NEXT_PUBLIC_API_URL",
            "NEXT_PUBLIC_API_URL_CLOUD",
            "API_PUBLIC_URL",
            "WEB_PUBLIC_URL",
            "SUPABASE_URL",
        ):
            if not v:
                print(f"{k}: EMPTY")
            else:
                try:
                    u = urlparse(v)
                    print(
                        f"{k}: SET scheme={u.scheme} host={u.hostname} "
                        f"path={u.path or '/'} (no query/creds shown)"
                    )
                except Exception:
                    print(f"{k}: SET (unparseable)")
        elif any(
            x in k
            for x in (
                "SECRET",
                "PASSWORD",
                "TOKEN",
                "ACCESS_KEY",
                "KEY_ID",
                "KEY_SECRET",
            )
        ):
            print(f"{k}: {classify_token(k, v)}")
        else:
            # Non-secret config may show length / emptiness only for safety
            if k in ("SUPABASE_PROJECT_REF", "SUPABASE_DB_REGION", "S3_BUCKET", "S3_REGION", "STORAGE_ADAPTER", "STORAGE_ADAPTER_CLOUD", "ENV", "DEPLOYMENT"):
                # project ref / region / bucket names are identifiers, not secrets — still be conservative
                shown = v if v and len(v) < 80 and " " not in v else ("SET" if v else "EMPTY")
                if k in ("SUPABASE_PROJECT_REF", "S3_BUCKET", "S3_REGION", "SUPABASE_DB_REGION", "STORAGE_ADAPTER", "STORAGE_ADAPTER_CLOUD"):
                    print(f"{k}: {shown if v else 'EMPTY'}")
                else:
                    print(f"{k}: {'SET' if v else 'EMPTY'}" + (f" value={v}" if v and k in ("ENV",) else ""))
            else:
                print(f"{k}: {'SET' if v else 'EMPTY'}")

    # Required for P3.7A checklist
    required = [
        "SUPABASE_PROJECT_REF",
        "SUPABASE_URL",
        "SUPABASE_ACCESS_TOKEN",
        "OWNER_DATABASE_URL_CLOUD",
        "APP_DATABASE_URL_CLOUD",
        "APP_ROLE_PASSWORD_CLOUD",
        "S3_ENDPOINT_URL",
        "S3_BUCKET",
        "S3_REGION",
        "S3_ACCESS_KEY",
        "S3_SECRET_KEY",
        "JWT_SECRET_CLOUD",
        "ALLOWED_ORIGINS_CLOUD",
        "API_PUBLIC_URL",
    ]
    have = {k for k, _ in pairs}
    filled = {k for k, v in pairs if v}
    print("--- p37a checklist ---")
    for k in required:
        if k not in have:
            print(f"{k}: MISSING_KEY")
        elif k not in filled:
            print(f"{k}: PRESENT_EMPTY")
        else:
            print(f"{k}: PRESENT_FILLED")


if __name__ == "__main__":
    main()
