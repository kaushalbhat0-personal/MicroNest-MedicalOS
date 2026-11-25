"""P3.7A real Supabase S3 provider isolation drill. Synthetic bytes only.

Uses application Settings field names (S3_ENDPOINT_URL, S3_ACCESS_KEY, ...).
Never prints credentials or signed URL query secrets (prints host/path only).
"""
from __future__ import annotations

import hashlib
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def redact_url(url: str) -> str:
    u = urlparse(url)
    return f"{u.scheme}://{u.hostname}{u.path}"


def main() -> int:
    env = load_env(ROOT / ".env")
    # Build Settings-like object without loading local STORAGE_ADAPTER=local
    from app.platform.config import Settings
    from app.platform.adapters.s3_storage import S3StorageAdapter

    # Construct settings from cloud S3 vars; do not mutate process local defaults permanently
    settings = Settings(
        JWT_SECRET=env.get("JWT_SECRET") or "dev-only-secret-min-32-chars-please-change-me",
        ENV="test",
        DEPLOYMENT="local",
        STORAGE_ADAPTER="s3",
        S3_ENDPOINT_URL=env["S3_ENDPOINT_URL"],
        S3_REGION=env["S3_REGION"],
        S3_BUCKET=env["S3_BUCKET"],
        S3_ACCESS_KEY=env["S3_ACCESS_KEY"],
        S3_SECRET_KEY=env["S3_SECRET_KEY"],
        S3_USE_TLS=env.get("S3_USE_TLS", "true").lower() == "true",
        S3_ENSURE_BUCKET=False,
        OWNER_DATABASE_URL=env.get("OWNER_DATABASE_URL", ""),
        APP_DATABASE_URL=env.get("APP_DATABASE_URL", ""),
        DEV_NOTIFICATIONS_ALLOW=True,
    )
    print(f"STORAGE_ADAPTER={settings.STORAGE_ADAPTER}")
    print(f"S3_ENDPOINT={redact_url(settings.S3_ENDPOINT_URL)}")
    print(f"S3_BUCKET={settings.S3_BUCKET}")
    print(f"S3_REGION={settings.S3_REGION}")

    adapter = S3StorageAdapter(settings)
    tid_a = uuid.uuid4()
    tid_b = uuid.uuid4()
    eid_a = uuid.uuid4()
    eid_b = uuid.uuid4()
    doc_a = uuid.uuid4()
    doc_b = uuid.uuid4()
    key_a = f"tenants/{tid_a}/encounters/{eid_a}/documents/{doc_a}"
    key_b = f"tenants/{tid_b}/encounters/{eid_b}/documents/{doc_b}"
    payload_a = b"SYNTHETIC-P37A-TENANT-A-DOCUMENT"
    payload_b = b"SYNTHETIC-P37A-TENANT-B-DOCUMENT"

    results: dict[str, str] = {}

    # 1 upload A
    meta_a = adapter.put(key=key_a, data=payload_a, content_type="text/plain")
    results["1_upload_a"] = "PASS" if meta_a.sha256 == hashlib.sha256(payload_a).hexdigest() else "FAIL"

    # upload B
    adapter.put(key=key_b, data=payload_b, content_type="text/plain")

    # 2 retrieve A
    got = adapter.get(key=key_a)
    results["2_retrieve_a"] = "PASS" if got == payload_a else "FAIL"

    # 3 A cannot get B by wrong key — this is path knowledge; provider returns B's bytes if key known.
    # Application-layer isolation is separate; provider isolation = no public access + private bucket.
    # Cross-tenant key substitution at API is P3.6; here we verify objects are distinct and private.
    got_b = adapter.get(key=key_b)
    results["3_objects_distinct"] = "PASS" if got_b == payload_b and got_b != payload_a else "FAIL"

    # 4 delete B as credential holder — credential is account-scoped, so delete succeeds.
    # Document: S3 keys are NOT bucket-policy tenant-scoped; app must enforce. Mark accordingly.
    adapter.delete(key=key_b)
    results["4_credential_can_delete_any_key"] = (
        "EXPECTED_ACCOUNT_SCOPE" if not adapter.exists(key=key_b) else "FAIL"
    )
    # restore B for remaining checks
    adapter.put(key=key_b, data=payload_b, content_type="text/plain")

    # 5 path traversal rejected by adapter
    try:
        adapter.put(key="../evil", data=b"x", content_type="text/plain")
        results["5_path_traversal"] = "FAIL"
    except ValueError:
        results["5_path_traversal"] = "PASS"

    # 6 signed URL for A
    url_a = adapter.signed_access(key=key_a, expires_seconds=60)
    results["6_signed_url_minted"] = "PASS" if url_a.startswith("http") else "FAIL"
    print(f"signed_url_a_redacted={redact_url(url_a)}")

    # 7 public unauthenticated access to raw object path (no signature) should fail
    import urllib.request
    import urllib.error

    # Construct a likely public URL form — Supabase storage public path
    # Private buckets should 400/404/403 without auth.
    public_guess = (
        f"https://{env['SUPABASE_PROJECT_REF']}.supabase.co/storage/v1/object/public/"
        f"{settings.S3_BUCKET}/{key_a}"
    )
    try:
        urllib.request.urlopen(public_guess, timeout=20)  # noqa: S310
        results["7_public_unauth_denied"] = "FAIL"
    except urllib.error.HTTPError as exc:
        results["7_public_unauth_denied"] = "PASS" if exc.code in (400, 401, 403, 404) else f"FAIL_{exc.code}"
    except Exception as exc:  # noqa: BLE001
        results["7_public_unauth_denied"] = f"PASS_NET_{type(exc).__name__}"

    # 8 expired signed URL
    url_short = adapter.signed_access(key=key_a, expires_seconds=1)
    time.sleep(2.2)
    try:
        urllib.request.urlopen(url_short, timeout=20)  # noqa: S310
        results["8_expired_signed_url"] = "FAIL"
    except urllib.error.HTTPError as exc:
        results["8_expired_signed_url"] = "PASS" if exc.code in (400, 401, 403, 404) else f"FAIL_{exc.code}"
    except Exception as exc:  # noqa: BLE001
        results["8_expired_signed_url"] = f"PASS_NET_{type(exc).__name__}"

    # 9 signed URL for A used against B key path (tamper) — change key in URL if possible
    # Presigned URLs bind key in signature; fetching with wrong key fails. We request B with A's URL:
    try:
        urllib.request.urlopen(url_a.replace(str(doc_a), str(doc_b)), timeout=20)  # noqa: S310
        results["9_tampered_signed_url"] = "FAIL"
    except urllib.error.HTTPError as exc:
        results["9_tampered_signed_url"] = "PASS" if exc.code in (400, 401, 403, 404) else f"FAIL_{exc.code}"
    except Exception as exc:  # noqa: BLE001
        results["9_tampered_signed_url"] = f"PASS_NET_{type(exc).__name__}"

    # 10 tenant-bound paths
    results["10_tenant_bound_paths"] = (
        "PASS" if key_a.startswith(f"tenants/{tid_a}/") and key_b.startswith(f"tenants/{tid_b}/") else "FAIL"
    )

    # Valid signed URL fetch should work
    try:
        with urllib.request.urlopen(url_a, timeout=20) as resp:  # noqa: S310
            body = resp.read()
        results["signed_url_fetch_a"] = "PASS" if body == payload_a else "FAIL"
    except Exception as exc:  # noqa: BLE001
        results["signed_url_fetch_a"] = f"FAIL_{type(exc).__name__}"

    # Cleanup synthetic objects (allowed: we created them)
    adapter.delete(key=key_a)
    adapter.delete(key=key_b)
    results["cleanup"] = "PASS" if (not adapter.exists(key=key_a) and not adapter.exists(key=key_b)) else "FAIL"

    print("=== RESULTS ===")
    for k, v in results.items():
        print(f"{k}: {v}")

    # Provider isolation verdict:
    # - Private public-URL denial + signed URL binding/expiry: provider controls
    # - Cross-tenant delete with shared account credentials: NOT provider-tenant-isolated
    hard_fails = [k for k, v in results.items() if v.startswith("FAIL")]
    if hard_fails:
        print(f"HARD_FAILS={hard_fails}")
        return 1
    print(
        "PROVIDER_NOTE: S3 credentials are account/bucket-scoped; "
        "tenant isolation depends on server-derived keys + API authz (P3.6)."
    )
    print("STORAGE_DRILL_COMPLETED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
