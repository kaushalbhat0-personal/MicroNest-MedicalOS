"""P3.7B env readiness — names only, no values."""
from pathlib import Path
from urllib.parse import urlparse

env: dict[str, str] = {}
for line in Path(".env").read_text(encoding="utf-8").splitlines():
    s = line.strip()
    if not s or s.startswith("#") or "=" not in s:
        continue
    k, v = s.split("=", 1)
    env[k.strip()] = v.strip()


def shape(url: str) -> str:
    if not url:
        return "EMPTY"
    u = urlparse(url.replace("postgresql+psycopg2://", "postgresql://", 1))
    user = u.username or "?"
    if user.startswith("hos_"):
        user = user.split(".")[0]
    elif user.startswith("postgres"):
        user = "postgres*"
    return f"user={user} host_class={'pooler' if u.hostname and 'pooler' in u.hostname else u.hostname} db={(u.path or '').lstrip('/')} ssl={'sslmode' in (u.query or '')}"


required_render = [
    "APP_DATABASE_URL",  # mapped from CLOUD at deploy time
    "JWT_SECRET",
    "ALLOWED_ORIGINS",
    "STORAGE_ADAPTER",
    "S3_ENDPOINT_URL",
    "S3_BUCKET",
    "S3_REGION",
    "S3_ACCESS_KEY",
    "S3_SECRET_KEY",
    "ENV",
    "DEPLOYMENT",
    "COOKIE_SECURE",
    "DB_SSL_REQUIRE",
    "NOTIFY_PROVIDER",
    "SAAS_PAYMENT_PROVIDER",
]

print("=== local URLs (must stay localhost) ===")
print("OWNER_DATABASE_URL", shape(env.get("OWNER_DATABASE_URL", "")))
print("APP_DATABASE_URL", shape(env.get("APP_DATABASE_URL", "")))

print("=== cloud staging sources ===")
for k in (
    "OWNER_DATABASE_URL_CLOUD",
    "APP_DATABASE_URL_CLOUD",
    "JWT_SECRET_CLOUD",
    "ALLOWED_ORIGINS_CLOUD",
    "API_PUBLIC_URL_CLOUD",
    "RENDER_API_SERVICE_NAME",
    "STORAGE_ADAPTER_CLOUD",
    "S3_ENDPOINT_URL",
    "S3_BUCKET",
    "S3_ACCESS_KEY",
    "S3_SECRET_KEY",
    "SAAS_PAYMENT_PROVIDER_CLOUD",
):
    v = env.get(k, "")
    if "DATABASE_URL" in k:
        print(f"{k}: {shape(v)}")
    elif k in ("ALLOWED_ORIGINS_CLOUD", "RENDER_API_SERVICE_NAME", "S3_BUCKET", "STORAGE_ADAPTER_CLOUD"):
        print(f"{k}: {v if v else 'EMPTY'}")
    else:
        print(f"{k}: {'SET' if v else 'EMPTY'}" + (f" len>={len(v.encode())}" if k.startswith("JWT") and v else ""))

print("=== Render runtime mapping readiness ===")
print("APP_DATABASE_URL <- APP_DATABASE_URL_CLOUD:", "READY" if env.get("APP_DATABASE_URL_CLOUD") else "MISSING")
print("JWT_SECRET <- JWT_SECRET_CLOUD:", "READY" if len(env.get("JWT_SECRET_CLOUD", "").encode()) >= 32 else "MISSING")
print("ALLOWED_ORIGINS <- ALLOWED_ORIGINS_CLOUD:", "READY" if env.get("ALLOWED_ORIGINS_CLOUD") else "MISSING")
print("API_PUBLIC_URL <- API_PUBLIC_URL_CLOUD:", "READY" if env.get("API_PUBLIC_URL_CLOUD") else "SET_AFTER_SERVICE_CREATE")
print("S3_*:", "READY" if all(env.get(k) for k in ("S3_ENDPOINT_URL", "S3_BUCKET", "S3_ACCESS_KEY", "S3_SECRET_KEY")) else "MISSING")
print("RENDER_API_KEY:", "MISSING (dashboard-only path)")
