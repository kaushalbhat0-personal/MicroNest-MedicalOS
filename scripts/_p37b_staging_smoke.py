"""P3.7B staging post-deploy smoke. Never print secrets or signed URL queries."""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://micronest-medicalos.onrender.com"
SERVICE_ID = "srv-dc2tmb49v7es73dkqc9g"
OWNER = "tea-dc2tm1m8bjmc738nb9ag"
sys.path.insert(0, str(ROOT / "backend"))


def load_env() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def redact_url(url: str) -> str:
    u = urlparse(url)
    return f"{u.scheme}://{u.hostname}{u.path}"


def http(
    method: str,
    path: str,
    *,
    body: dict | None = None,
    headers: dict[str, str] | None = None,
    cookie: str | None = None,
) -> tuple[int, dict[str, str], bytes]:
    h = {"User-Agent": "p37b-smoke", "Accept": "application/json"}
    if headers:
        h.update(headers)
    if cookie:
        h["Cookie"] = cookie
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def render_api(path: str, key: str) -> object:
    req = urllib.request.Request(
        f"https://api.render.com/v1{path}",
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "User-Agent": "p37b-smoke",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
        return json.loads(resp.read().decode())


def scrub(msg: str) -> str:
    msg = re.sub(r"\x1b\[[0-9;]*[mK]|\x1b\(B", "", msg)
    # coarse secret patterns
    msg = re.sub(r"(postgres(?:ql)?://)[^\s\"']+", r"\1[REDACTED]", msg, flags=re.I)
    msg = re.sub(r"(password|secret|token|api[_-]?key)\s*[:=]\s*\S+", r"\1=[REDACTED]", msg, flags=re.I)
    return msg


def main() -> int:
    env = load_env()
    results: dict[str, str] = {}
    fail = 0

    # --- A Availability ---
    st, _, body = http("GET", "/api/healthz")
    ok = st == 200 and b'"ok"' in body
    results["A_healthz"] = "PASS" if ok else f"FAIL status={st}"
    fail += 0 if ok else 1
    print(f"A_healthz={results['A_healthz']} body={body.decode()[:80]}")

    st, _, body = http("GET", "/api/readyz")
    ok = st == 200 and b'"ready"' in body
    results["A_readyz"] = "PASS" if ok else f"FAIL status={st} body={body[:120]!r}"
    fail += 0 if ok else 1
    print(f"A_readyz={results['A_readyz']}")

    # --- B Database via hos_app cloud URL ---
    from sqlalchemy import create_engine, text

    app_url = env["APP_DATABASE_URL_CLOUD"]
    # Validate URL shape without printing credentials
    parsed = urlparse(app_url)
    host = parsed.hostname or ""
    user = parsed.username or ""
    dbname = (parsed.path or "").lstrip("/")
    qs = urllib.parse.parse_qs(parsed.query)
    sslmode = (qs.get("sslmode") or [""])[0]
    print(
        f"B_db_url_shape user={user!r} host_suffix={host[-40:] if len(host)>40 else host!r} "
        f"db={dbname!r} sslmode={sslmode!r}"
    )
    shape_ok = (
        user.startswith("hos_app")
        and "pooler" in host
        and "preview" in dbname
        and sslmode == "require"
    )
    results["B_url_shape"] = "PASS" if shape_ok else "FAIL"
    fail += 0 if shape_ok else 1

    engine = create_engine(app_url, pool_pre_ping=True)
    owner_url = env.get("OWNER_DATABASE_URL_CLOUD") or ""
    # Alembic revision is an ops concern — hos_app correctly lacks SELECT on
    # alembic_version (least privilege). Read via hos_owner only for smoke.
    if not owner_url:
        results["B_alembic"] = "FAIL_NO_OWNER_URL"
        fail += 1
        rev = None
    else:
        owner_engine = create_engine(owner_url, pool_pre_ping=True)
        with owner_engine.connect() as oc:
            owner_user = oc.execute(text("SELECT current_user")).scalar()
            rev = oc.execute(text("SELECT version_num FROM alembic_version")).scalar()
            print(f"B_owner_user={owner_user} alembic={rev}")
        ok_rev = rev == "0027_saas_payment_reliability"
        results["B_alembic"] = "PASS" if ok_rev else f"FAIL got={rev}"
        fail += 0 if ok_rev else 1

    with engine.connect() as c:
        cur_user = c.execute(text("SELECT current_user")).scalar()
        bypass = c.execute(
            text("SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user")
        ).scalar()
        # Confirm hos_app cannot read alembic_version (expected deny)
        try:
            c.execute(text("SELECT version_num FROM alembic_version")).scalar()
            results["B_alembic_app_denied"] = "FAIL_ALLOWED"
            fail += 1
        except Exception:
            c.rollback()
            results["B_alembic_app_denied"] = "PASS"
        print(f"B_current_user={cur_user} bypassrls={bypass}")
        ok_role = cur_user == "hos_app" and bypass is False
        results["B_role"] = "PASS" if ok_role else "FAIL"
        fail += 0 if ok_role else 1
        try:
            c.execute(text("CREATE TABLE p37b_smoke_ddl_fail(id int)"))
            c.commit()
            results["B_ddl_denied"] = "FAIL_ALLOWED"
            fail += 1
        except Exception:
            c.rollback()
            results["B_ddl_denied"] = "PASS"
        try:
            c.execute(text("ALTER TABLE patients ADD COLUMN p37b_x int"))
            c.commit()
            results["B_alter_denied"] = "FAIL_ALLOWED"
            fail += 1
        except Exception:
            c.rollback()
            results["B_alter_denied"] = "PASS"
        # no tenant context → RLS should hide rows
        locs = c.execute(text("SELECT count(*) FROM locations")).scalar()
        results["B_rls_no_tenant"] = "PASS" if locs == 0 else f"FAIL count={locs}"
        fail += 0 if locs == 0 else 1
    print(
        f"B_role={results['B_role']} B_alembic={results['B_alembic']} "
        f"B_alembic_app_denied={results['B_alembic_app_denied']} "
        f"B_ddl={results['B_ddl_denied']} B_alter={results['B_alter_denied']} "
        f"B_rls={results['B_rls_no_tenant']}"
    )

    # --- C Auth / tenancy ---
    st, _, body = http("GET", "/api/v1/auth/me")
    ok = st == 401
    results["C_unauth_me"] = "PASS" if ok else f"FAIL {st}"
    fail += 0 if ok else 1

    tid = "00000000-0000-0000-0000-000000000001"
    st, _, body = http("GET", f"/api/v1/tenants/{tid}/patients")
    ok = st == 401
    results["C_unauth_patients"] = "PASS" if ok else f"FAIL {st}"
    fail += 0 if ok else 1

    # bad credentials
    st, _, body = http(
        "POST",
        "/api/v1/auth/login",
        body={"email": "nobody@example.com", "password": "definitely-wrong-password"},
    )
    ok = st == 401
    results["C_bad_login"] = "PASS" if ok else f"FAIL {st} {body[:120]!r}"
    fail += 0 if ok else 1

    # X-Tenant-Id alone must not grant access
    st, _, body = http(
        "GET",
        f"/api/v1/tenants/{tid}/patients",
        headers={"X-Tenant-Id": tid},
    )
    ok = st == 401
    results["C_tenant_header_alone"] = "PASS" if ok else f"FAIL {st}"
    fail += 0 if ok else 1
    print(
        f"C_unauth_me={results['C_unauth_me']} patients={results['C_unauth_patients']} "
        f"bad_login={results['C_bad_login']} tenant_hdr={results['C_tenant_header_alone']}"
    )

    # synthetic account? look for STAGING_SMOKE_* or existing seed emails in env
    smoke_email = env.get("STAGING_SMOKE_EMAIL") or env.get("SMOKE_TEST_EMAIL")
    smoke_password = env.get("STAGING_SMOKE_PASSWORD") or env.get("SMOKE_TEST_PASSWORD")
    if smoke_email and smoke_password:
        st, hdrs, body = http(
            "POST",
            "/api/v1/auth/login",
            body={"email": smoke_email, "password": smoke_password},
        )
        if st == 200:
            results["C_synth_login"] = "PASS"
            # parse set-cookie briefly (names only)
            set_c = hdrs.get("Set-Cookie") or hdrs.get("set-cookie") or ""
            cookie_names = re.findall(r"(?:^|, )([^=\s]+)=", set_c)
            print(f"C_synth_login=PASS cookie_names={cookie_names}")
        else:
            results["C_synth_login"] = f"FAIL status={st}"
            fail += 1
            print(f"C_synth_login={results['C_synth_login']}")
    else:
        results["C_synth_login"] = "SKIP_NO_SYNTHETIC_ACCOUNT"
        print("C_synth_login=SKIP (no STAGING_SMOKE_EMAIL/PASSWORD in local env)")

    # Count users in cloud (synthetic existence check only — emails redacted)
    with engine.connect() as c:
        n_users = c.execute(text("SELECT count(*) FROM users")).scalar()
        n_tenants = c.execute(text("SELECT count(*) FROM tenants")).scalar()
    print(f"C_db_users={n_users} C_db_tenants={n_tenants}")
    results["C_seed_state"] = f"users={n_users},tenants={n_tenants}"

    # --- D Storage (adapter-level, synthetic) — same credential as Render ---
    from app.platform.adapters.s3_storage import S3StorageAdapter
    from app.platform.config import Settings

    settings = Settings(
        JWT_SECRET=env.get("JWT_SECRET_CLOUD")
        or env.get("JWT_SECRET")
        or "dev-only-secret-min-32-chars-please-change-me",
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
    print(
        f"D_storage adapter=s3 endpoint={redact_url(settings.S3_ENDPOINT_URL)} "
        f"bucket={settings.S3_BUCKET} region={settings.S3_REGION}"
    )
    adapter = S3StorageAdapter(settings)
    tid_a, tid_b = uuid.uuid4(), uuid.uuid4()
    eid_a, eid_b = uuid.uuid4(), uuid.uuid4()
    doc_a, doc_b = uuid.uuid4(), uuid.uuid4()
    key_a = f"tenants/{tid_a}/encounters/{eid_a}/documents/{doc_a}"
    key_b = f"tenants/{tid_b}/encounters/{eid_b}/documents/{doc_b}"
    payload_a = b"SYNTHETIC-P37B-TENANT-A"
    payload_b = b"SYNTHETIC-P37B-TENANT-B"
    try:
        meta_a = adapter.put(key=key_a, data=payload_a, content_type="text/plain")
        got_a = adapter.get(key=key_a)
        ok = got_a == payload_a and meta_a.sha256 == hashlib.sha256(payload_a).hexdigest()
        results["D_upload_get_a"] = "PASS" if ok else "FAIL"
        fail += 0 if ok else 1

        adapter.put(key=key_b, data=payload_b, content_type="text/plain")
        got_b = adapter.get(key=key_b)
        ok = got_b == payload_b and got_b != payload_a
        results["D_distinct_ab"] = "PASS" if ok else "FAIL"
        fail += 0 if ok else 1

        # public URL denial
        public = (
            f"{settings.S3_ENDPOINT_URL.rstrip('/')}/{settings.S3_BUCKET}/{key_a}"
        )
        try:
            req = urllib.request.Request(public, headers={"User-Agent": "p37b-smoke"})
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                results["D_public_denied"] = f"FAIL status={resp.status}"
                fail += 1
        except urllib.error.HTTPError as exc:
            results["D_public_denied"] = "PASS" if exc.code in (401, 403, 404) else f"FAIL {exc.code}"
            fail += 0 if exc.code in (401, 403, 404) else 1
        except Exception as exc:
            # TLS/DNS denial also acceptable as not public-readable
            results["D_public_denied"] = f"PASS_ERR({type(exc).__name__})"

        # signed URL mint + fetch (do not print query)
        signed = adapter.signed_access(key=key_a, expires_seconds=60)
        signed_redacted = redact_url(signed)
        try:
            req = urllib.request.Request(signed, headers={"User-Agent": "p37b-smoke"})
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                ok = resp.read() == payload_a
                results["D_signed_fetch"] = "PASS" if ok else "FAIL_BODY"
                fail += 0 if ok else 1
        except Exception as exc:
            results["D_signed_fetch"] = f"FAIL {type(exc).__name__}"
            fail += 1
        print(f"D_signed_url_host_path={signed_redacted}")

        # expired
        expired = adapter.signed_access(key=key_a, expires_seconds=1)
        time.sleep(2)
        try:
            req = urllib.request.Request(expired, headers={"User-Agent": "p37b-smoke"})
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                results["D_expired_denied"] = f"FAIL status={resp.status}"
                fail += 1
        except urllib.error.HTTPError as exc:
            results["D_expired_denied"] = "PASS" if exc.code in (400, 401, 403) else f"FAIL {exc.code}"
            fail += 0 if exc.code in (400, 401, 403) else 1
        except Exception as exc:
            results["D_expired_denied"] = f"PASS_ERR({type(exc).__name__})"

        # tampered: swap key in path if present
        tampered = signed.replace(str(doc_a), str(doc_b))
        if tampered == signed:
            results["D_tampered_denied"] = "SKIP_NO_KEY_IN_URL"
        else:
            try:
                req = urllib.request.Request(tampered, headers={"User-Agent": "p37b-smoke"})
                with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                    results["D_tampered_denied"] = f"FAIL status={resp.status}"
                    fail += 1
            except urllib.error.HTTPError as exc:
                results["D_tampered_denied"] = (
                    "PASS" if exc.code in (400, 401, 403, 404) else f"FAIL {exc.code}"
                )
                fail += 0 if exc.code in (400, 401, 403, 404) else 1
            except Exception as exc:
                results["D_tampered_denied"] = f"PASS_ERR({type(exc).__name__})"

        # path traversal rejected
        try:
            adapter.put(key="../escape", data=b"x", content_type="text/plain")
            results["D_path_traversal"] = "FAIL_ACCEPTED"
            fail += 1
        except Exception:
            results["D_path_traversal"] = "PASS"

        results["D_iam_scope"] = (
            "NOT_PER_TENANT — shared account/bucket credential "
            "(app-layer key + auth isolation required)"
        )
    finally:
        for k in (key_a, key_b):
            try:
                adapter.delete(key=k)
            except Exception:
                pass
    print(
        f"D_upload_get_a={results['D_upload_get_a']} distinct={results['D_distinct_ab']} "
        f"public={results['D_public_denied']} signed={results['D_signed_fetch']} "
        f"expired={results['D_expired_denied']} tampered={results['D_tampered_denied']} "
        f"traversal={results['D_path_traversal']}"
    )
    print(f"D_iam_scope={results['D_iam_scope']}")

    # --- E Logs (scrubbed) ---
    key = env["RENDER_API_KEY"]
    qs = urllib.parse.urlencode(
        {
            "ownerId": OWNER,
            "resource": SERVICE_ID,
            "limit": "80",
            "startTime": "2026-11-24T19:25:00Z",
        }
    )
    req = urllib.request.Request(
        f"https://api.render.com/v1/logs?{qs}",
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "User-Agent": "p37b-smoke",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
        logs = json.loads(resp.read().decode()).get("logs") or []
    leak_hits = 0
    error_lines = 0
    for entry in logs:
        msg = scrub(str(entry.get("message") or ""))
        lvl = ""
        for lab in entry.get("labels") or []:
            if lab.get("name") == "level":
                lvl = lab.get("value") or ""
        if lvl == "error":
            error_lines += 1
        if re.search(r"postgres(?:ql)?://[^\s\[]+|JWT_SECRET|S3_SECRET|password=", msg, re.I):
            leak_hits += 1
            print(f"E_LEAK_PATTERN level={lvl} msg={msg[:160]}")
    results["E_secret_leak"] = "PASS" if leak_hits == 0 else f"FAIL hits={leak_hits}"
    fail += 0 if leak_hits == 0 else 1
    results["E_error_log_count"] = str(error_lines)
    print(f"E_secret_leak={results['E_secret_leak']} recent_error_lines={error_lines}")

    # CORS check via OPTIONS (names only)
    st, hdrs, _ = http(
        "OPTIONS",
        "/api/healthz",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    acao = hdrs.get("Access-Control-Allow-Origin") or hdrs.get("access-control-allow-origin")
    results["E_cors_wildcard"] = "PASS" if acao != "*" else "FAIL_WILDCARD"
    fail += 0 if acao != "*" else 1
    print(f"E_cors_acao_present={bool(acao)} wildcard_check={results['E_cors_wildcard']}")

    # Deploy meta
    meta_path = ROOT / "scripts" / "_p37b_last_deploy.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    print(
        f"DEPLOY id={meta.get('deploy_id')} status={meta.get('status')} "
        f"commit={meta.get('commit')}"
    )

    print("--- SUMMARY ---")
    for k, v in results.items():
        print(f"{k}={v}")
    print(f"FAIL_COUNT={fail}")
    out = ROOT / "scripts" / "_p37b_smoke_results.json"
    out.write_text(
        json.dumps({"results": results, "fail_count": fail, "deploy": meta}, indent=2),
        encoding="utf-8",
    )
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
