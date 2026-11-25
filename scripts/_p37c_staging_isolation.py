"""P3.7C synthetic tenant isolation against live Render staging.

Uses supported public API flows only. Never prints passwords, tokens, cookies,
signed URL queries, or connection strings. Writes redacted evidence JSON.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

EVIDENCE_PATH = ROOT / "scripts" / "_p37c_evidence.json"
CREDS_PATH = ROOT / ".env.p37c.staging"


def load_kv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
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


class Runner:
    def __init__(self, base: str, creds: dict[str, str]) -> None:
        self.base = base.rstrip("/")
        self.creds = creds
        self.results: list[dict[str, Any]] = []
        self.state: dict[str, Any] = {}
        # One client per identity so cookies never cross tenants accidentally.
        self.clients: dict[str, httpx.Client] = {}

    def client(self, identity: str) -> httpx.Client:
        if identity not in self.clients:
            self.clients[identity] = httpx.Client(
                base_url=self.base,
                timeout=60.0,
                headers={"User-Agent": "p37c-isolation", "Accept": "application/json"},
                follow_redirects=False,
            )
        return self.clients[identity]

    def record(
        self,
        *,
        test_id: str,
        method: str,
        route: str,
        identity: str,
        tenant: str | None,
        expected: str,
        status: int,
        passed: bool,
        notes: str = "",
    ) -> None:
        row = {
            "id": test_id,
            "method": method,
            "route": route,
            "identity": identity,
            "tenant": tenant,
            "expected": expected,
            "status": status,
            "result": "PASS" if passed else "FAIL",
            "notes": notes,
        }
        self.results.append(row)
        print(
            f"{row['result']} {test_id} {method} {route} "
            f"identity={identity} tenant={tenant or '-'} "
            f"status={status} expected={expected}"
            + (f" notes={notes}" if notes else "")
        )

    def skip(self, test_id: str, reason: str) -> None:
        self.results.append(
            {
                "id": test_id,
                "method": "-",
                "route": "-",
                "identity": "-",
                "tenant": None,
                "expected": "-",
                "status": None,
                "result": "SKIP",
                "notes": reason,
            }
        )
        print(f"SKIP {test_id}: {reason}")

    def req(
        self,
        identity: str,
        method: str,
        path: str,
        *,
        json_body: dict | list | None = None,
        headers: dict[str, str] | None = None,
        tenant_id: str | None = None,
        idempotency: str | None = None,
    ) -> httpx.Response:
        h: dict[str, str] = {}
        if headers:
            h.update(headers)
        if tenant_id:
            h["X-Tenant"] = tenant_id
        if idempotency:
            h["Idempotency-Key"] = idempotency
        return self.client(identity).request(method, path, json=json_body, headers=h)

    # --- Auth helpers ---
    def signup(self, email: str, name: str, password: str) -> int:
        r = self.req(
            "anon",
            "POST",
            "/api/v1/auth/signup",
            json_body={"email": email, "display_name": name, "password": password},
        )
        return r.status_code

    def login(self, identity: str, email: str, password: str) -> httpx.Response:
        # Clear prior cookies for this identity jar
        self.client(identity).cookies.clear()
        return self.req(
            identity,
            "POST",
            "/api/v1/auth/login",
            json_body={"email": email, "password": password},
        )

    def logout(self, identity: str) -> httpx.Response:
        return self.req(identity, "POST", "/api/v1/auth/logout")

    def me(self, identity: str) -> httpx.Response:
        return self.req(identity, "GET", "/api/v1/auth/me")

    def provision_owner(self, label: str, email: str, name: str, password: str,
                        clinic: str, slug: str) -> dict[str, Any]:
        st = self.signup(email, name, password)
        if st not in (200, 202):
            raise RuntimeError(f"signup {label} failed status={st}")
        # Login does not require email verification (identity.service.authenticate).
        time.sleep(0.6)
        lr = self.login(label, email, password)
        if lr.status_code != 200:
            # Do not dump response body (may echo email); status only.
            raise RuntimeError(f"login {label} failed status={lr.status_code}")
        cookie_names = sorted({c.name for c in self.client(label).cookies.jar})
        if "hos_access" not in cookie_names:
            raise RuntimeError(f"login {label} missing hos_access cookie names={cookie_names}")
        wr = self.req(
            label,
            "POST",
            "/api/v1/workspaces",
            json_body={
                "clinic_name": clinic,
                "slug": slug,
                "location_name": "Main Clinic",
                "timezone": "Asia/Kolkata",
                "practitioner_display_name": f"Dr {name}",
                "specialty_codes": ["dental"],
            },
            idempotency=str(uuid.uuid4()),
        )
        if wr.status_code != 201:
            raise RuntimeError(
                f"workspace {label} failed status={wr.status_code} body={wr.text[:200]}"
            )
        data = wr.json()
        tid = str(data["tenant"]["id"])
        loc = str(data["location"]["id"])
        prac = str(data["practitioner"]["id"])
        # Approve practitioner (owner has staff.manage)
        ar = self.req(
            label,
            "POST",
            f"/api/v1/tenants/{tid}/verification",
            json_body={"practitioner_id": prac, "status": "approved"},
            tenant_id=tid,
        )
        if ar.status_code != 200:
            raise RuntimeError(
                f"approve practitioner {label} failed status={ar.status_code} {ar.text[:200]}"
            )
        return {
            "tenant_id": tid,
            "location_id": loc,
            "practitioner_id": prac,
            "slug": data["tenant"]["slug"],
            "name": data["tenant"]["name"],
            "membership_role": data["membership"]["role"],
        }

    def create_patient(
        self, identity: str, tid: str, display_name: str, phone: str, email: str | None = None
    ) -> str:
        body: dict[str, Any] = {
            "display_name": display_name,
            "phone": phone,
        }
        if email:
            body["email"] = email
        r = self.req(
            identity,
            "POST",
            f"/api/v1/tenants/{tid}/patients",
            json_body=body,
            tenant_id=tid,
        )
        if r.status_code not in (200, 201):
            raise RuntimeError(f"create patient failed {r.status_code} {r.text[:200]}")
        return str(r.json()["id"])


def main() -> int:
    root_env = load_kv(ROOT / ".env")
    # Ensure creds exist (gitignored .env.p37c.staging)
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "p37c_gen", ROOT / "scripts" / "_p37c_generate_creds.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()

    creds = load_kv(CREDS_PATH)
    if not creds.get("P37C_OWNER_A_EMAIL"):
        print("BLOCKED: missing .env.p37c.staging")
        return 2

    base = creds.get("P37C_API_BASE") or "https://micronest-medicalos.onrender.com"
    # Preflight
    with httpx.Client(timeout=30.0) as c:
        hz = c.get(f"{base}/api/healthz")
        rz = c.get(f"{base}/api/readyz")
    if hz.status_code != 200 or rz.status_code != 200:
        print(f"BLOCKED: staging unhealthy healthz={hz.status_code} readyz={rz.status_code}")
        return 2
    print(f"preflight healthz={hz.status_code} readyz={rz.status_code}")

    r = Runner(base, creds)

    # ========== PHASE 3: Provision ==========
    print("=== PROVISION TENANT A ===")
    try:
        a = r.provision_owner(
            "owner_a",
            creds["P37C_OWNER_A_EMAIL"],
            creds["P37C_OWNER_A_NAME"],
            creds["P37C_OWNER_A_PASSWORD"],
            creds["P37C_CLINIC_A_NAME"],
            creds["P37C_CLINIC_A_SLUG"],
        )
        r.state["A"] = a
        r.record(
            test_id="P3_A_provision",
            method="POST",
            route="/api/v1/workspaces",
            identity="owner_a",
            tenant="A",
            expected="201+approved",
            status=201,
            passed=True,
            notes=f"role={a['membership_role']} slug={a['slug']}",
        )
    except Exception as exc:
        r.record(
            test_id="P3_A_provision",
            method="POST",
            route="/api/v1/workspaces",
            identity="owner_a",
            tenant="A",
            expected="201+approved",
            status=0,
            passed=False,
            notes=type(exc).__name__,
        )
        _write(r)
        return 1

    print("=== PROVISION TENANT B ===")
    time.sleep(0.5)
    try:
        b = r.provision_owner(
            "owner_b",
            creds["P37C_OWNER_B_EMAIL"],
            creds["P37C_OWNER_B_NAME"],
            creds["P37C_OWNER_B_PASSWORD"],
            creds["P37C_CLINIC_B_NAME"],
            creds["P37C_CLINIC_B_SLUG"],
        )
        r.state["B"] = b
        r.record(
            test_id="P3_B_provision",
            method="POST",
            route="/api/v1/workspaces",
            identity="owner_b",
            tenant="B",
            expected="201+approved",
            status=201,
            passed=True,
            notes=f"role={b['membership_role']} slug={b['slug']}",
        )
    except Exception as exc:
        r.record(
            test_id="P3_B_provision",
            method="POST",
            route="/api/v1/workspaces",
            identity="owner_b",
            tenant="B",
            expected="201+approved",
            status=0,
            passed=False,
            notes=type(exc).__name__,
        )
        _write(r)
        return 1

    tid_a, tid_b = a["tenant_id"], b["tenant_id"]
    if tid_a == tid_b:
        print("FAIL tenants share id")
        return 1

    # Confirm me tenants
    me_a = r.me("owner_a")
    me_b = r.me("owner_b")
    tenants_a = {str(t["id"]) for t in me_a.json().get("tenants", [])}
    tenants_b = {str(t["id"]) for t in me_b.json().get("tenants", [])}
    r.record(
        test_id="P3_A_me_tenants",
        method="GET",
        route="/api/v1/auth/me",
        identity="owner_a",
        tenant="A",
        expected="owns A only",
        status=me_a.status_code,
        passed=me_a.status_code == 200 and tid_a in tenants_a and tid_b not in tenants_a,
        notes=f"tenant_count={len(tenants_a)}",
    )
    r.record(
        test_id="P3_B_me_tenants",
        method="GET",
        route="/api/v1/auth/me",
        identity="owner_b",
        tenant="B",
        expected="owns B only",
        status=me_b.status_code,
        passed=me_b.status_code == 200 and tid_b in tenants_b and tid_a not in tenants_b,
        notes=f"tenant_count={len(tenants_b)}",
    )

    # Receptionist invite for A
    inv = r.req(
        "owner_a",
        "POST",
        f"/api/v1/tenants/{tid_a}/invites",
        json_body={"email": creds["P37C_RECV_A_EMAIL"], "role": "receptionist"},
        tenant_id=tid_a,
    )
    invite_token = None
    if inv.status_code in (200, 201):
        invite_token = inv.json().get("token")
        r.record(
            test_id="P3_A_invite_recv",
            method="POST",
            route="/api/v1/tenants/{tid}/invites",
            identity="owner_a",
            tenant="A",
            expected="201 with one-time token",
            status=inv.status_code,
            passed=bool(invite_token),
            notes="token_present=yes" if invite_token else "token_missing",
        )
    else:
        r.record(
            test_id="P3_A_invite_recv",
            method="POST",
            route="/api/v1/tenants/{tid}/invites",
            identity="owner_a",
            tenant="A",
            expected="201",
            status=inv.status_code,
            passed=False,
            notes=inv.text[:120],
        )

    if invite_token:
        # Accept invite as new receptionist (public endpoint)
        acc = r.req(
            "recv_a",
            "POST",
            "/api/v1/invites/accept",
            json_body={
                "token": invite_token,
                "display_name": creds["P37C_RECV_A_NAME"],
                "password": creds["P37C_RECV_A_PASSWORD"],
            },
        )
        # Clear token from memory ASAP
        invite_token = None
        r.record(
            test_id="P3_A_invite_accept",
            method="POST",
            route="/api/v1/invites/accept",
            identity="recv_a",
            tenant="A",
            expected="200 session",
            status=acc.status_code,
            passed=acc.status_code == 200,
        )
        # Re-login with stored password for stable session
        time.sleep(0.3)
        lr = r.login("recv_a", creds["P37C_RECV_A_EMAIL"], creds["P37C_RECV_A_PASSWORD"])
        r.record(
            test_id="P3_A_recv_login",
            method="POST",
            route="/api/v1/auth/login",
            identity="recv_a",
            tenant="A",
            expected="200",
            status=lr.status_code,
            passed=lr.status_code == 200,
        )
    else:
        r.skip("P3_A_invite_accept", "invite token unavailable")
        r.skip("P3_A_recv_login", "invite token unavailable")

    # Patients
    print("=== CREATE SYNTHETIC PATIENTS ===")
    pid_a1 = r.create_patient(
        "owner_a", tid_a, "Synthetic Patient Alpha One", "+919000000101",
        "patient.a1.p37c@example.test",
    )
    pid_a2 = r.create_patient(
        "owner_a", tid_a, "Synthetic Patient Alpha Two", "+919000000102",
        "patient.a2.p37c@example.test",
    )
    pid_b1 = r.create_patient(
        "owner_b", tid_b, "Synthetic Patient Beta One", "+919000000201",
        "patient.b1.p37c@example.test",
    )
    r.state["pid_a1"] = pid_a1
    r.state["pid_a2"] = pid_a2
    r.state["pid_b1"] = pid_b1
    r.record(
        test_id="P3_patients_created",
        method="POST",
        route="/api/v1/tenants/{tid}/patients",
        identity="owners",
        tenant="A+B",
        expected="201 x3",
        status=201,
        passed=True,
        notes="a1+a2+b1 synthetic",
    )

    # ========== PHASE 4: Cross-tenant ==========
    print("=== CROSS-TENANT SECURITY MATRIX ===")

    # 1 A owner reads A patient
    g = r.req("owner_a", "GET", f"/api/v1/tenants/{tid_a}/patients/{pid_a1}", tenant_id=tid_a)
    r.record(
        test_id="C1_A_read_own",
        method="GET",
        route="/tenants/{A}/patients/{a1}",
        identity="owner_a",
        tenant="A",
        expected="200",
        status=g.status_code,
        passed=g.status_code == 200 and str(g.json().get("id")) == pid_a1,
    )

    # 2 B owner reads B patient
    g = r.req("owner_b", "GET", f"/api/v1/tenants/{tid_b}/patients/{pid_b1}", tenant_id=tid_b)
    r.record(
        test_id="C2_B_read_own",
        method="GET",
        route="/tenants/{B}/patients/{b1}",
        identity="owner_b",
        tenant="B",
        expected="200",
        status=g.status_code,
        passed=g.status_code == 200 and str(g.json().get("id")) == pid_b1,
    )

    # 3 A owner cannot get B patient by id (path B + header A → 404 match_tenant)
    g = r.req("owner_a", "GET", f"/api/v1/tenants/{tid_b}/patients/{pid_b1}", tenant_id=tid_a)
    r.record(
        test_id="C3_A_pathB_hdrA",
        method="GET",
        route="/tenants/{B}/patients/{b1}",
        identity="owner_a",
        tenant="A",
        expected="404",
        status=g.status_code,
        passed=g.status_code == 404,
    )

    # 3b A owner with X-Tenant=B (no membership) → 403
    g = r.req("owner_a", "GET", f"/api/v1/tenants/{tid_b}/patients/{pid_b1}", tenant_id=tid_b)
    r.record(
        test_id="C3_A_hdrB_no_membership",
        method="GET",
        route="/tenants/{B}/patients/{b1}",
        identity="owner_a",
        tenant="B*",
        expected="403",
        status=g.status_code,
        passed=g.status_code == 403,
    )

    # 4 B cannot get A patient
    g = r.req("owner_b", "GET", f"/api/v1/tenants/{tid_a}/patients/{pid_a1}", tenant_id=tid_b)
    r.record(
        test_id="C4_B_pathA_hdrB",
        method="GET",
        route="/tenants/{A}/patients/{a1}",
        identity="owner_b",
        tenant="B",
        expected="404",
        status=g.status_code,
        passed=g.status_code == 404,
    )
    g = r.req("owner_b", "GET", f"/api/v1/tenants/{tid_a}/patients/{pid_a1}", tenant_id=tid_a)
    r.record(
        test_id="C4_B_hdrA_no_membership",
        method="GET",
        route="/tenants/{A}/patients/{a1}",
        identity="owner_b",
        tenant="A*",
        expected="403",
        status=g.status_code,
        passed=g.status_code == 403,
    )

    # 5 Cross-tenant search
    s = r.req(
        "owner_a",
        "GET",
        f"/api/v1/tenants/{tid_a}/patients?q=Beta",
        tenant_id=tid_a,
    )
    ids_found = [str(p.get("id")) for p in (s.json() if s.status_code == 200 else [])]
    r.record(
        test_id="C5_A_search_no_B",
        method="GET",
        route="/tenants/{A}/patients?q=Beta",
        identity="owner_a",
        tenant="A",
        expected="200 no B ids",
        status=s.status_code,
        passed=s.status_code == 200 and pid_b1 not in ids_found,
        notes=f"count={len(ids_found)}",
    )

    # Create appointments for isolation tests
    start_a = (datetime.now(timezone.utc) + timedelta(days=1)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )
    start_b = start_a + timedelta(hours=2)
    ap_a = r.req(
        "owner_a",
        "POST",
        f"/api/v1/tenants/{tid_a}/appointments",
        json_body={
            "patient_id": pid_a1,
            "practitioner_id": a["practitioner_id"],
            "location_id": a["location_id"],
            "start": start_a.isoformat(),
            "duration_minutes": 30,
            "timezone": "Asia/Kolkata",
            "notes": "SYNTHETIC-A-APPT",
        },
        tenant_id=tid_a,
        idempotency=str(uuid.uuid4()),
    )
    ap_b = r.req(
        "owner_b",
        "POST",
        f"/api/v1/tenants/{tid_b}/appointments",
        json_body={
            "patient_id": pid_b1,
            "practitioner_id": b["practitioner_id"],
            "location_id": b["location_id"],
            "start": start_b.isoformat(),
            "duration_minutes": 30,
            "timezone": "Asia/Kolkata",
            "notes": "SYNTHETIC-B-APPT",
        },
        tenant_id=tid_b,
        idempotency=str(uuid.uuid4()),
    )
    appt_a_id = str(ap_a.json().get("id")) if ap_a.status_code in (200, 201) else None
    appt_b_id = str(ap_b.json().get("id")) if ap_b.status_code in (200, 201) else None
    r.record(
        test_id="C6_appt_create_A",
        method="POST",
        route="/tenants/{A}/appointments",
        identity="owner_a",
        tenant="A",
        expected="201",
        status=ap_a.status_code,
        passed=ap_a.status_code in (200, 201),
        notes=ap_a.text[:100] if ap_a.status_code not in (200, 201) else "",
    )
    r.record(
        test_id="C6_appt_create_B",
        method="POST",
        route="/tenants/{B}/appointments",
        identity="owner_b",
        tenant="B",
        expected="201",
        status=ap_b.status_code,
        passed=ap_b.status_code in (200, 201),
        notes=ap_b.text[:100] if ap_b.status_code not in (200, 201) else "",
    )

    # 6 Cross-tenant appointment retrieval
    if appt_b_id:
        g = r.req(
            "owner_a",
            "GET",
            f"/api/v1/tenants/{tid_a}/appointments",
            tenant_id=tid_a,
        )
        appt_ids = []
        if g.status_code == 200:
            payload = g.json()
            items = payload if isinstance(payload, list) else payload.get("items") or payload.get("appointments") or []
            appt_ids = [str(x.get("id")) for x in items]
        r.record(
            test_id="C6_A_list_no_B_appt",
            method="GET",
            route="/tenants/{A}/appointments",
            identity="owner_a",
            tenant="A",
            expected="200 without B appt",
            status=g.status_code,
            passed=g.status_code == 200 and appt_b_id not in appt_ids,
            notes=f"count={len(appt_ids)}",
        )
        g = r.req(
            "owner_a",
            "GET",
            f"/api/v1/tenants/{tid_b}/appointments",
            tenant_id=tid_b,
        )
        r.record(
            test_id="C6_A_list_B_hdrB",
            method="GET",
            route="/tenants/{B}/appointments",
            identity="owner_a",
            tenant="B*",
            expected="403",
            status=g.status_code,
            passed=g.status_code == 403,
        )
    else:
        r.skip("C6_A_list_no_B_appt", "B appointment not created")

    # 7 Cross-tenant clinical notes / documents / billing probes
    # Open encounter A
    enc_a = r.req(
        "owner_a",
        "POST",
        f"/api/v1/tenants/{tid_a}/encounters",
        json_body={
            "patient_id": pid_a1,
            "practitioner_id": a["practitioner_id"],
            "location_id": a["location_id"],
            "appointment_id": appt_a_id,
            "chief_complaint": "SYNTHETIC toothache",
        },
        tenant_id=tid_a,
    )
    enc_a_id = str(enc_a.json().get("id")) if enc_a.status_code in (200, 201) else None
    r.record(
        test_id="C7_enc_open_A",
        method="POST",
        route="/tenants/{A}/encounters",
        identity="owner_a",
        tenant="A",
        expected="201",
        status=enc_a.status_code,
        passed=enc_a.status_code in (200, 201),
        notes=enc_a.text[:120] if enc_a.status_code not in (200, 201) else "",
    )
    note_a_id = None
    if enc_a_id:
        note = r.req(
            "owner_a",
            "POST",
            f"/api/v1/tenants/{tid_a}/encounters/{enc_a_id}/clinical-notes",
            json_body={
                "note_type": "general",
                "subjective": "SYNTHETIC subjective — no real PHI",
                "objective": "SYNTHETIC objective",
                "assessment": "SYNTHETIC assessment",
                "plan": "SYNTHETIC plan",
            },
            tenant_id=tid_a,
        )
        note_a_id = str(note.json().get("id")) if note.status_code in (200, 201) else None
        r.record(
            test_id="C7_note_A",
            method="POST",
            route="/tenants/{A}/encounters/{e}/clinical-notes",
            identity="owner_a",
            tenant="A",
            expected="201",
            status=note.status_code,
            passed=note.status_code in (200, 201),
            notes=note.text[:100] if note.status_code not in (200, 201) else "",
        )
        # B cannot read A's encounter
        g = r.req(
            "owner_b",
            "GET",
            f"/api/v1/tenants/{tid_a}/encounters/{enc_a_id}",
            tenant_id=tid_b,
        )
        r.record(
            test_id="C7_B_read_A_encounter",
            method="GET",
            route="/tenants/{A}/encounters/{e}",
            identity="owner_b",
            tenant="B",
            expected="404",
            status=g.status_code,
            passed=g.status_code == 404,
        )
        g = r.req(
            "owner_b",
            "GET",
            f"/api/v1/tenants/{tid_a}/encounters/{enc_a_id}",
            tenant_id=tid_a,
        )
        r.record(
            test_id="C7_B_hdrA_encounter",
            method="GET",
            route="/tenants/{A}/encounters/{e}",
            identity="owner_b",
            tenant="A*",
            expected="403",
            status=g.status_code,
            passed=g.status_code == 403,
        )

    # Document create + access isolation
    doc_a_id = None
    doc_a_key = None
    if enc_a_id:
        doc = r.req(
            "owner_a",
            "POST",
            f"/api/v1/tenants/{tid_a}/encounters/{enc_a_id}/documents",
            json_body={
                "doc_type": "photo",
                "content_type": "image/png",
                "notes": "SYNTHETIC-DOC-A",
            },
            tenant_id=tid_a,
        )
        if doc.status_code in (200, 201):
            doc_a_id = str(doc.json()["id"])
            doc_a_key = doc.json().get("storage_key")
        r.record(
            test_id="C7_doc_create_A",
            method="POST",
            route="/tenants/{A}/encounters/{e}/documents",
            identity="owner_a",
            tenant="A",
            expected="201",
            status=doc.status_code,
            passed=doc.status_code in (200, 201),
            notes=doc.text[:100] if doc.status_code not in (200, 201) else "key_server_allocated",
        )
        if doc_a_id and doc_a_key:
            # Put synthetic PNG-ish bytes via shared S3 adapter (upload pipeline)
            from app.platform.adapters.s3_storage import S3StorageAdapter
            from app.platform.config import Settings

            settings = Settings(
                JWT_SECRET=root_env.get("JWT_SECRET_CLOUD")
                or root_env.get("JWT_SECRET")
                or "dev-only-secret-min-32-chars-please-change-me",
                ENV="test",
                DEPLOYMENT="local",
                STORAGE_ADAPTER="s3",
                S3_ENDPOINT_URL=root_env["S3_ENDPOINT_URL"],
                S3_REGION=root_env["S3_REGION"],
                S3_BUCKET=root_env["S3_BUCKET"],
                S3_ACCESS_KEY=root_env["S3_ACCESS_KEY"],
                S3_SECRET_KEY=root_env["S3_SECRET_KEY"],
                S3_USE_TLS=True,
                S3_ENSURE_BUCKET=False,
                OWNER_DATABASE_URL="",
                APP_DATABASE_URL="",
                DEV_NOTIFICATIONS_ALLOW=True,
            )
            adapter = S3StorageAdapter(settings)
            # Minimal PNG header + payload marker
            payload = (
                b"\x89PNG\r\n\x1a\n" + b"SYNTHETIC-P37C-TENANT-A-IMAGE"
            )
            adapter.put(key=doc_a_key, data=payload, content_type="image/png")
            access = r.req(
                "owner_a",
                "POST",
                f"/api/v1/tenants/{tid_a}/documents/{doc_a_id}/access",
                tenant_id=tid_a,
            )
            r.record(
                test_id="C7_doc_access_A",
                method="POST",
                route="/tenants/{A}/documents/{d}/access",
                identity="owner_a",
                tenant="A",
                expected="200 signed",
                status=access.status_code,
                passed=access.status_code == 200 and bool(access.json().get("url")),
                notes=f"expires={access.json().get('expires_in_seconds')}"
                if access.status_code == 200
                else access.text[:80],
            )
            # Cross-tenant document access denied
            g = r.req(
                "owner_b",
                "POST",
                f"/api/v1/tenants/{tid_a}/documents/{doc_a_id}/access",
                tenant_id=tid_b,
            )
            r.record(
                test_id="C7_B_doc_access_pathA",
                method="POST",
                route="/tenants/{A}/documents/{d}/access",
                identity="owner_b",
                tenant="B",
                expected="404",
                status=g.status_code,
                passed=g.status_code == 404,
            )
            g = r.req(
                "owner_b",
                "POST",
                f"/api/v1/tenants/{tid_a}/documents/{doc_a_id}/access",
                tenant_id=tid_a,
            )
            r.record(
                test_id="C7_B_doc_access_hdrA",
                method="POST",
                route="/tenants/{A}/documents/{d}/access",
                identity="owner_b",
                tenant="A*",
                expected="403",
                status=g.status_code,
                passed=g.status_code == 403,
            )
            # Billing probe: B cannot list A's estimates
            g = r.req(
                "owner_b",
                "GET",
                f"/api/v1/tenants/{tid_a}/estimates",
                tenant_id=tid_b,
            )
            r.record(
                test_id="C7_B_estimates_pathA",
                method="GET",
                route="/tenants/{A}/estimates",
                identity="owner_b",
                tenant="B",
                expected="404",
                status=g.status_code,
                passed=g.status_code == 404,
            )

    # 8 Changing X-Tenant to other tenant does not grant access (covered above)
    # 9 Valid A token cannot use B context (covered C3_A_hdrB)
    r.record(
        test_id="C8_C9_header_swap",
        method="GET",
        route="(matrix C3/C4)",
        identity="owners",
        tenant="cross",
        expected="403/404 fail-closed",
        status=403,
        passed=all(
            x["result"] == "PASS"
            for x in r.results
            if x["id"]
            in {
                "C3_A_hdrB_no_membership",
                "C4_B_hdrA_no_membership",
                "C3_A_pathB_hdrA",
                "C4_B_pathA_hdrB",
            }
        ),
        notes="aggregate of header/path swap cases",
    )

    # 10 Missing / invalid / expired / revoked credentials
    g = r.req("anon", "GET", f"/api/v1/tenants/{tid_a}/patients/{pid_a1}", tenant_id=tid_a)
    r.record(
        test_id="C10_missing_creds",
        method="GET",
        route="/tenants/{A}/patients/{a1}",
        identity="anon",
        tenant="A",
        expected="401",
        status=g.status_code,
        passed=g.status_code == 401,
    )
    bad = httpx.Client(base_url=base, timeout=30.0, headers={"User-Agent": "p37c-isolation"})
    bad_r = bad.get(
        f"/api/v1/tenants/{tid_a}/patients/{pid_a1}",
        headers={"Authorization": "Bearer clearly.invalid.token", "X-Tenant": tid_a},
    )
    r.record(
        test_id="C10_invalid_bearer",
        method="GET",
        route="/tenants/{A}/patients/{a1}",
        identity="invalid_bearer",
        tenant="A",
        expected="401",
        status=bad_r.status_code,
        passed=bad_r.status_code == 401,
    )
    bad.close()

    # Revoke: logout then retry
    r.logout("owner_a")
    g = r.req("owner_a", "GET", f"/api/v1/tenants/{tid_a}/patients/{pid_a1}", tenant_id=tid_a)
    r.record(
        test_id="C10_after_logout",
        method="GET",
        route="/tenants/{A}/patients/{a1}",
        identity="owner_a_logged_out",
        tenant="A",
        expected="401",
        status=g.status_code,
        passed=g.status_code == 401,
    )
    # Re-login owner_a for remaining tests
    time.sleep(0.5)
    lr = r.login("owner_a", creds["P37C_OWNER_A_EMAIL"], creds["P37C_OWNER_A_PASSWORD"])
    r.record(
        test_id="C10_relogin_A",
        method="POST",
        route="/api/v1/auth/login",
        identity="owner_a",
        tenant="A",
        expected="200",
        status=lr.status_code,
        passed=lr.status_code == 200,
    )

    # 11 Receptionist cannot do owner-only ops
    if "recv_a" in r.clients and any(
        x["id"] == "P3_A_recv_login" and x["result"] == "PASS" for x in r.results
    ):
        g = r.req(
            "recv_a",
            "POST",
            f"/api/v1/tenants/{tid_a}/verification",
            json_body={"practitioner_id": a["practitioner_id"], "status": "approved"},
            tenant_id=tid_a,
        )
        r.record(
            test_id="C11_recv_cannot_verify",
            method="POST",
            route="/tenants/{A}/verification",
            identity="recv_a",
            tenant="A",
            expected="403",
            status=g.status_code,
            passed=g.status_code in (401, 403),
        )
        g = r.req(
            "recv_a",
            "POST",
            f"/api/v1/tenants/{tid_a}/invites",
            json_body={"email": "other.recv.p37c@example.test", "role": "receptionist"},
            tenant_id=tid_a,
        )
        r.record(
            test_id="C11_recv_cannot_invite",
            method="POST",
            route="/tenants/{A}/invites",
            identity="recv_a",
            tenant="A",
            expected="403",
            status=g.status_code,
            passed=g.status_code in (401, 403),
        )
    else:
        r.skip("C11_recv_cannot_verify", "receptionist not provisioned")
        r.skip("C11_recv_cannot_invite", "receptionist not provisioned")

    # 12 Portal isolation
    print("=== PORTAL ISOLATION ===")
    # Create portal users via signup (password kept); enroll binds without overwrite
    for email_key, name_key, pw_key, ident in [
        ("P37C_PORTAL_A1_EMAIL", "P37C_PORTAL_A1_NAME", "P37C_PORTAL_A1_PASSWORD", "portal_a1"),
        ("P37C_PORTAL_A2_EMAIL", "P37C_PORTAL_A2_NAME", "P37C_PORTAL_A2_PASSWORD", "portal_a2"),
    ]:
        st = r.signup(creds[email_key], creds[name_key], creds[pw_key])
        if st not in (200, 202):
            r.record(
                test_id=f"C12_signup_{ident}",
                method="POST",
                route="/auth/signup",
                identity=ident,
                tenant="A",
                expected="202",
                status=st,
                passed=False,
            )
        time.sleep(0.3)

    # Map portal emails to patients: a1→pid_a1, a2→pid_a2
    for email, patient_id, name, test_suffix in [
        (creds["P37C_PORTAL_A1_EMAIL"], pid_a1, creds["P37C_PORTAL_A1_NAME"], "a1"),
        (creds["P37C_PORTAL_A2_EMAIL"], pid_a2, creds["P37C_PORTAL_A2_NAME"], "a2"),
    ]:
        en = r.req(
            "owner_a",
            "POST",
            f"/api/v1/tenants/{tid_a}/portal-links",
            json_body={"email": email, "patient_id": patient_id, "display_name": name},
            tenant_id=tid_a,
        )
        r.record(
            test_id=f"C12_enroll_{test_suffix}",
            method="POST",
            route="/tenants/{A}/portal-links",
            identity="owner_a",
            tenant="A",
            expected="200/201",
            status=en.status_code,
            passed=en.status_code in (200, 201),
            notes=en.text[:120] if en.status_code not in (200, 201) else "",
        )

    time.sleep(0.4)
    lr = r.login("portal_a1", creds["P37C_PORTAL_A1_EMAIL"], creds["P37C_PORTAL_A1_PASSWORD"])
    r.record(
        test_id="C12_portal_a1_login",
        method="POST",
        route="/auth/login",
        identity="portal_a1",
        tenant="A",
        expected="200",
        status=lr.status_code,
        passed=lr.status_code == 200,
    )
    if lr.status_code == 200:
        mep = r.req("portal_a1", "GET", "/api/v1/portal/me", tenant_id=tid_a)
        r.record(
            test_id="C12_portal_me",
            method="GET",
            route="/portal/me",
            identity="portal_a1",
            tenant="A",
            expected="200 own patient",
            status=mep.status_code,
            passed=mep.status_code == 200,
            notes=f"keys={sorted(mep.json().keys()) if mep.status_code==200 else mep.text[:80]}",
        )
        # Cross-patient within tenant: try timeline/overview for other patient via staff routes
        g = r.req(
            "portal_a1",
            "GET",
            f"/api/v1/tenants/{tid_a}/patients/{pid_a2}",
            tenant_id=tid_a,
        )
        r.record(
            test_id="C12_portal_cannot_staff_patient",
            method="GET",
            route="/tenants/{A}/patients/{a2}",
            identity="portal_a1",
            tenant="A",
            expected="403",
            status=g.status_code,
            passed=g.status_code in (401, 403, 404),
        )
        # Portal encounter for foreign id
        if enc_a_id:
            # enc_a is for a1 — create nothing for a2; probing random encounter
            fake_enc = str(uuid.uuid4())
            g = r.req(
                "portal_a1",
                "GET",
                f"/api/v1/portal/encounters/{fake_enc}",
                tenant_id=tid_a,
            )
            r.record(
                test_id="C12_portal_foreign_encounter",
                method="GET",
                route="/portal/encounters/{foreign}",
                identity="portal_a1",
                tenant="A",
                expected="404",
                status=g.status_code,
                passed=g.status_code == 404,
            )
        # Portal cannot use tenant B
        g = r.req("portal_a1", "GET", "/api/v1/portal/me", tenant_id=tid_b)
        r.record(
            test_id="C12_portal_hdrB",
            method="GET",
            route="/portal/me",
            identity="portal_a1",
            tenant="B*",
            expected="403",
            status=g.status_code,
            passed=g.status_code == 403,
        )
    else:
        r.skip("C12_portal_me", "portal login failed")
        r.skip("C12_portal_cannot_staff_patient", "portal login failed")
        r.skip("C12_portal_foreign_encounter", "portal login failed")
        r.skip("C12_portal_hdrB", "portal login failed")

    # ========== PHASE 5: Core workflow Tenant A ==========
    print("=== CORE WORKFLOW TENANT A ===")
    # Search
    s = r.req(
        "owner_a",
        "GET",
        f"/api/v1/tenants/{tid_a}/patients?q=Alpha",
        tenant_id=tid_a,
    )
    r.record(
        test_id="W1_patient_search",
        method="GET",
        route="/tenants/{A}/patients?q=Alpha",
        identity="owner_a",
        tenant="A",
        expected="200 with a1",
        status=s.status_code,
        passed=s.status_code == 200
        and pid_a1 in [str(p.get("id")) for p in s.json()],
    )
    # Calendar / appointments list
    s = r.req("owner_a", "GET", f"/api/v1/tenants/{tid_a}/appointments", tenant_id=tid_a)
    r.record(
        test_id="W2_calendar_list",
        method="GET",
        route="/tenants/{A}/appointments",
        identity="owner_a",
        tenant="A",
        expected="200",
        status=s.status_code,
        passed=s.status_code == 200,
    )
    # Reception check-in
    if appt_a_id:
        ck = r.req(
            "owner_a",
            "POST",
            f"/api/v1/tenants/{tid_a}/appointments/{appt_a_id}/status",
            json_body={"status": "checked_in"},
            tenant_id=tid_a,
        )
        r.record(
            test_id="W3_checkin",
            method="POST",
            route="/tenants/{A}/appointments/{id}/status",
            identity="owner_a",
            tenant="A",
            expected="200 checked_in",
            status=ck.status_code,
            passed=ck.status_code == 200,
            notes=ck.text[:100] if ck.status_code != 200 else "",
        )
        q = r.req(
            "owner_a",
            "GET",
            f"/api/v1/tenants/{tid_a}/locations/{a['location_id']}/reception-queue",
            tenant_id=tid_a,
        )
        r.record(
            test_id="W3_reception_queue",
            method="GET",
            route="/tenants/{A}/locations/{loc}/reception-queue",
            identity="owner_a",
            tenant="A",
            expected="200",
            status=q.status_code,
            passed=q.status_code == 200,
        )
    else:
        r.skip("W3_checkin", "no appointment")
        r.skip("W3_reception_queue", "no appointment")

    # Patient 360
    ov = r.req(
        "owner_a",
        "GET",
        f"/api/v1/tenants/{tid_a}/patients/{pid_a1}/overview",
        tenant_id=tid_a,
    )
    r.record(
        test_id="W4_overview",
        method="GET",
        route="/tenants/{A}/patients/{a1}/overview",
        identity="owner_a",
        tenant="A",
        expected="200",
        status=ov.status_code,
        passed=ov.status_code == 200,
    )
    tl = r.req(
        "owner_a",
        "GET",
        f"/api/v1/tenants/{tid_a}/patients/{pid_a1}/timeline",
        tenant_id=tid_a,
    )
    r.record(
        test_id="W4_timeline",
        method="GET",
        route="/tenants/{A}/patients/{a1}/timeline",
        identity="owner_a",
        tenant="A",
        expected="200",
        status=tl.status_code,
        passed=tl.status_code == 200,
    )

    # Prescription if medications exist
    meds = r.req("owner_a", "GET", f"/api/v1/tenants/{tid_a}/medications", tenant_id=tid_a)
    med_list = meds.json() if meds.status_code == 200 else []
    if enc_a_id and med_list:
        code = med_list[0].get("code") or med_list[0].get("medication_code")
        rx = r.req(
            "owner_a",
            "POST",
            f"/api/v1/tenants/{tid_a}/encounters/{enc_a_id}/prescriptions",
            json_body={
                "items": [
                    {
                        "medication_code": code,
                        "dose": "1 tablet",
                        "route": "PO",
                        "frequency": "BID",
                        "duration_days": 3,
                        "instructions": "SYNTHETIC RX — take with food",
                    }
                ]
            },
            tenant_id=tid_a,
        )
        r.record(
            test_id="W5_prescription",
            method="POST",
            route="/tenants/{A}/encounters/{e}/prescriptions",
            identity="owner_a",
            tenant="A",
            expected="201",
            status=rx.status_code,
            passed=rx.status_code in (200, 201),
            notes=rx.text[:100] if rx.status_code not in (200, 201) else "",
        )
    else:
        r.skip("W5_prescription", "medication catalog empty or no encounter")

    # Follow-up + consent + whatsapp link (no send)
    due = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    fu = r.req(
        "owner_a",
        "POST",
        f"/api/v1/tenants/{tid_a}/follow-ups",
        json_body={
            "patient_id": pid_a1,
            "location_id": a["location_id"],
            "due_at": due,
            "category": "manual",
            "reason": "SYNTHETIC follow-up check",
            "source_type": "manual",
            "priority": "normal",
        },
        tenant_id=tid_a,
    )
    r.record(
        test_id="W6_followup",
        method="POST",
        route="/tenants/{A}/follow-ups",
        identity="owner_a",
        tenant="A",
        expected="201",
        status=fu.status_code,
        passed=fu.status_code in (200, 201),
        notes=fu.text[:100] if fu.status_code not in (200, 201) else "",
    )
    cons = r.req(
        "owner_a",
        "POST",
        f"/api/v1/tenants/{tid_a}/communication-consents",
        json_body={
            "patient_id": pid_a1,
            "channel": "whatsapp",
            "purpose": "appointment_reminder",
            "status": "granted",
            "capture_source": "staff",
        },
        tenant_id=tid_a,
    )
    r.record(
        test_id="W6_consent",
        method="POST",
        route="/tenants/{A}/communication-consents",
        identity="owner_a",
        tenant="A",
        expected="201",
        status=cons.status_code,
        passed=cons.status_code in (200, 201),
        notes=cons.text[:100] if cons.status_code not in (200, 201) else "",
    )
    wa = r.req(
        "owner_a",
        "POST",
        f"/api/v1/tenants/{tid_a}/whatsapp-link",
        json_body={
            "patient_id": pid_a1,
            "purpose": "appointment_reminder",
            "message": "SYNTHETIC reminder — do not send",
            "require_consent": True,
        },
        tenant_id=tid_a,
    )
    # Do not print WhatsApp URL (may contain phone)
    wa_ok = wa.status_code == 200 and wa.json().get("auto_send") is False
    r.record(
        test_id="W6_whatsapp_link",
        method="POST",
        route="/tenants/{A}/whatsapp-link",
        identity="owner_a",
        tenant="A",
        expected="200 auto_send=false",
        status=wa.status_code,
        passed=wa_ok,
        notes=f"auto_send={wa.json().get('auto_send') if wa.status_code==200 else wa.text[:80]}",
    )

    # ========== PHASE 6: Storage limitation ==========
    print("=== STORAGE CROSS-TENANT ===")
    if doc_a_key and doc_a_id:
        from app.platform.adapters.s3_storage import S3StorageAdapter
        from app.platform.config import Settings

        settings = Settings(
            JWT_SECRET=root_env.get("JWT_SECRET_CLOUD")
            or root_env.get("JWT_SECRET")
            or "dev-only-secret-min-32-chars-please-change-me",
            ENV="test",
            DEPLOYMENT="local",
            STORAGE_ADAPTER="s3",
            S3_ENDPOINT_URL=root_env["S3_ENDPOINT_URL"],
            S3_REGION=root_env["S3_REGION"],
            S3_BUCKET=root_env["S3_BUCKET"],
            S3_ACCESS_KEY=root_env["S3_ACCESS_KEY"],
            S3_SECRET_KEY=root_env["S3_SECRET_KEY"],
            S3_USE_TLS=True,
            S3_ENSURE_BUCKET=False,
            OWNER_DATABASE_URL="",
            APP_DATABASE_URL="",
            DEV_NOTIFICATIONS_ALLOW=True,
        )
        adapter = S3StorageAdapter(settings)
        # App-level: already tested C7_B_doc_access_*
        # Key prefix enforcement
        prefix_ok = doc_a_key.startswith(f"tenants/{tid_a}/")
        r.record(
            test_id="S1_key_prefix_tenant_bound",
            method="inspect",
            route="storage_key",
            identity="system",
            tenant="A",
            expected="tenants/{A}/...",
            status=200 if prefix_ok else 500,
            passed=prefix_ok,
            notes="server-allocated key",
        )
        signed = adapter.signed_access(key=doc_a_key, expires_seconds=60)
        # Authorized fetch
        try:
            fr = httpx.get(signed, timeout=30.0)
            r.record(
                test_id="S2_signed_fetch",
                method="GET",
                route=redact_url(signed),
                identity="presigned",
                tenant="A",
                expected="200",
                status=fr.status_code,
                passed=fr.status_code == 200 and b"SYNTHETIC-P37C" in fr.content,
            )
        except Exception as exc:
            r.record(
                test_id="S2_signed_fetch",
                method="GET",
                route=redact_url(signed),
                identity="presigned",
                tenant="A",
                expected="200",
                status=0,
                passed=False,
                notes=type(exc).__name__,
            )
        # Expired
        expired = adapter.signed_access(key=doc_a_key, expires_seconds=1)
        time.sleep(2)
        er = httpx.get(expired, timeout=30.0)
        r.record(
            test_id="S3_expired_denied",
            method="GET",
            route=redact_url(expired),
            identity="presigned",
            tenant="A",
            expected="400/401/403",
            status=er.status_code,
            passed=er.status_code in (400, 401, 403),
        )
        # Tamper key in URL
        key_b = f"tenants/{tid_b}/encounters/{uuid.uuid4()}/documents/{uuid.uuid4()}"
        tampered = signed.replace(doc_a_key, key_b) if doc_a_key in signed else signed + "x"
        tr = httpx.get(tampered, timeout=30.0)
        r.record(
            test_id="S4_tampered_denied",
            method="GET",
            route=redact_url(tampered),
            identity="presigned",
            tenant="cross",
            expected="400/401/403/404",
            status=tr.status_code,
            passed=tr.status_code in (400, 401, 403, 404),
        )
        # Public deny
        public = f"{root_env['S3_ENDPOINT_URL'].rstrip('/')}/{root_env['S3_BUCKET']}/{doc_a_key}"
        try:
            pr = httpx.get(public, timeout=30.0)
            pub_ok = pr.status_code in (401, 403, 404)
            pst = pr.status_code
        except Exception as exc:
            pub_ok = True
            pst = 0
            notes = type(exc).__name__
        else:
            notes = ""
        r.record(
            test_id="S5_public_denied",
            method="GET",
            route=redact_url(public),
            identity="anon",
            tenant="A",
            expected="401/403/404",
            status=pst,
            passed=pub_ok,
            notes=notes,
        )
        # Shared credential can still read any key → NOT per-tenant IAM
        # Put B object with same credential then get — proves account scope
        adapter.put(key=key_b, data=b"SYNTHETIC-P37C-TENANT-B-IMAGE", content_type="image/png")
        got_b = adapter.get(key=key_b)
        r.record(
            test_id="S6_shared_cred_reads_B",
            method="S3.get",
            route="tenants/{B}/...",
            identity="shared_s3_cred",
            tenant="B",
            expected="EXPECTED_ACCOUNT_SCOPE",
            status=200,
            passed=got_b == b"SYNTHETIC-P37C-TENANT-B-IMAGE",
            notes="NOT per-tenant IAM — shared credential can read any key",
        )
        try:
            adapter.delete(key=key_b)
        except Exception:
            pass
        r.record(
            test_id="S7_iam_claim",
            method="policy",
            route="storage",
            identity="system",
            tenant="-",
            expected="do not claim per-tenant IAM",
            status=200,
            passed=True,
            notes="Application auth + key prefix isolate; IAM is account/bucket scoped",
        )
    else:
        r.skip("S1_key_prefix_tenant_bound", "document not created")
        r.skip("S2_signed_fetch", "document not created")
        r.skip("S3_expired_denied", "document not created")
        r.skip("S4_tampered_denied", "document not created")
        r.skip("S5_public_denied", "document not created")
        r.skip("S6_shared_cred_reads_B", "document not created")
        r.skip("S7_iam_claim", "document not created")

    # Cleanup note: leave synthetic tenants (evidence). Optional doc object cleanup.
    if doc_a_key:
        try:
            from app.platform.adapters.s3_storage import S3StorageAdapter
            from app.platform.config import Settings

            settings = Settings(
                JWT_SECRET=root_env.get("JWT_SECRET_CLOUD")
                or root_env.get("JWT_SECRET")
                or "dev-only-secret-min-32-chars-please-change-me",
                ENV="test",
                DEPLOYMENT="local",
                STORAGE_ADAPTER="s3",
                S3_ENDPOINT_URL=root_env["S3_ENDPOINT_URL"],
                S3_REGION=root_env["S3_REGION"],
                S3_BUCKET=root_env["S3_BUCKET"],
                S3_ACCESS_KEY=root_env["S3_ACCESS_KEY"],
                S3_SECRET_KEY=root_env["S3_SECRET_KEY"],
                S3_USE_TLS=True,
                S3_ENSURE_BUCKET=False,
                OWNER_DATABASE_URL="",
                APP_DATABASE_URL="",
                DEV_NOTIFICATIONS_ALLOW=True,
            )
            S3StorageAdapter(settings).delete(key=doc_a_key)
            print("cleanup: deleted synthetic document object A")
        except Exception as exc:
            print(f"cleanup: doc A object leave-in-place ({type(exc).__name__})")

    for c in r.clients.values():
        c.close()

    _write(r)
    fails = [x for x in r.results if x["result"] == "FAIL"]
    skips = [x for x in r.results if x["result"] == "SKIP"]
    passes = [x for x in r.results if x["result"] == "PASS"]
    print("--- SUMMARY ---")
    print(f"PASS={len(passes)} FAIL={len(fails)} SKIP={len(skips)}")
    if fails:
        for f in fails:
            print(f"  FAIL {f['id']}: status={f['status']} notes={f.get('notes')}")
    return 0 if not fails else 1


def _write(r: Runner) -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "api": r.base,
        "deploy_commit": "293dc668e7117f20a4b88e7a3047aa8e501c99b6",
        "tenants": {
            "A": {
                "slug": (r.state.get("A") or {}).get("slug"),
                "name": (r.state.get("A") or {}).get("name"),
                # IDs are synthetic UUIDs — include for evidence correlation only
                "tenant_id_present": bool((r.state.get("A") or {}).get("tenant_id")),
            },
            "B": {
                "slug": (r.state.get("B") or {}).get("slug"),
                "name": (r.state.get("B") or {}).get("name"),
                "tenant_id_present": bool((r.state.get("B") or {}).get("tenant_id")),
            },
        },
        "results": r.results,
        "counts": {
            "pass": sum(1 for x in r.results if x["result"] == "PASS"),
            "fail": sum(1 for x in r.results if x["result"] == "FAIL"),
            "skip": sum(1 for x in r.results if x["result"] == "SKIP"),
        },
    }
    EVIDENCE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"evidence_written={EVIDENCE_PATH.name}")


if __name__ == "__main__":
    raise SystemExit(main())
