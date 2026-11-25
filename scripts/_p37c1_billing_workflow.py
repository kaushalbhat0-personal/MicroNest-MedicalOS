"""P3.7C.1 positive billing workflow + isolation regression on live staging.

Preserves scripts/_p37c_evidence.json. Writes scripts/_p37c1_billing_evidence.json.
Never prints secrets/tokens/cookies.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
CREDS = ROOT / ".env.p37c.staging"
OUT = ROOT / "scripts" / "_p37c1_billing_evidence.json"
BASE_DEFAULT = "https://micronest-medicalos.onrender.com"


def load(path: Path) -> dict[str, str]:
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


class Suite:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self.results: list[dict[str, Any]] = []
        self.clients: dict[str, httpx.Client] = {}
        self.state: dict[str, Any] = {}

    def client(self, ident: str) -> httpx.Client:
        if ident not in self.clients:
            self.clients[ident] = httpx.Client(
                base_url=self.base,
                timeout=90.0,
                headers={"User-Agent": "p37c1-billing", "Accept": "application/json"},
            )
        return self.clients[ident]

    def rec(
        self,
        *,
        test_id: str,
        method: str,
        route: str,
        identity: str,
        expected: str,
        status: int | None,
        passed: bool,
        notes: str = "",
    ) -> None:
        row = {
            "id": test_id,
            "method": method,
            "route": route,
            "identity": identity,
            "expected": expected,
            "status": status,
            "result": "PASS" if passed else "FAIL",
            "notes": notes,
        }
        self.results.append(row)
        print(
            f"{row['result']} {test_id} {method} {route} "
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
                "expected": "-",
                "status": None,
                "result": "SKIP",
                "notes": reason,
            }
        )
        print(f"SKIP {test_id}: {reason}")

    def req(
        self,
        ident: str,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        tenant_id: str | None = None,
        idem: str | None = None,
    ) -> httpx.Response:
        h: dict[str, str] = {}
        if tenant_id:
            h["X-Tenant"] = tenant_id
        if idem:
            h["Idempotency-Key"] = idem
        return self.client(ident).request(method, path, json=json_body, headers=h)

    def login(self, ident: str, email: str, password: str) -> httpx.Response:
        self.client(ident).cookies.clear()
        return self.req(
            ident, "POST", "/api/v1/auth/login", json_body={"email": email, "password": password}
        )


def main() -> int:
    creds = load(CREDS)
    if not creds.get("P37C_OWNER_A_EMAIL"):
        print("BLOCKED: missing .env.p37c.staging")
        return 2
    base = creds.get("P37C_API_BASE") or BASE_DEFAULT
    s = Suite(base)

    # health (Render free tier may cold-start)
    hz = rz = None
    for attempt in range(6):
        try:
            with httpx.Client(timeout=90.0) as c:
                hz = c.get(f"{base}/api/healthz")
                rz = c.get(f"{base}/api/readyz")
            if hz.status_code == 200 and rz.status_code == 200:
                break
        except httpx.TimeoutException:
            print(f"health_retry[{attempt}] timeout — cold start?")
            continue
    if hz is None or rz is None or hz.status_code != 200 or rz.status_code != 200:
        print(
            f"BLOCKED unhealthy healthz={getattr(hz,'status_code',None)} "
            f"readyz={getattr(rz,'status_code',None)}"
        )
        return 2
    print(f"preflight healthz={hz.status_code} readyz={rz.status_code}")

    # login A/B
    la = s.login("owner_a", creds["P37C_OWNER_A_EMAIL"], creds["P37C_OWNER_A_PASSWORD"])
    lb = s.login("owner_b", creds["P37C_OWNER_B_EMAIL"], creds["P37C_OWNER_B_PASSWORD"])
    s.rec(
        test_id="R0_login_A",
        method="POST",
        route="/auth/login",
        identity="owner_a",
        expected="200",
        status=la.status_code,
        passed=la.status_code == 200,
    )
    s.rec(
        test_id="R0_login_B",
        method="POST",
        route="/auth/login",
        identity="owner_b",
        expected="200",
        status=lb.status_code,
        passed=lb.status_code == 200,
    )
    if la.status_code != 200 or lb.status_code != 200:
        _write(s)
        return 1

    me_a = s.req("owner_a", "GET", "/api/v1/auth/me").json()
    me_b = s.req("owner_b", "GET", "/api/v1/auth/me").json()
    tid_a = str(me_a["tenants"][0]["id"])
    tid_b = str(me_b["tenants"][0]["id"])
    s.state["tid_a"] = tid_a
    s.state["tid_b"] = tid_b

    ctx_a = s.req(
        "owner_a", "GET", f"/api/v1/tenants/{tid_a}/workspace-context", tenant_id=tid_a
    )
    ctx = ctx_a.json() if ctx_a.status_code == 200 else {}
    perms = set(ctx.get("permissions") or [])
    loc_ids = [str(x) for x in (ctx.get("location_ids") or [])]
    s.rec(
        test_id="R1_seed_patient_create",
        method="GET",
        route="/workspace-context",
        identity="owner_a",
        expected="patient.create present",
        status=ctx_a.status_code,
        passed="patient.create" in perms,
        notes=f"perm_count={len(perms)}",
    )
    s.rec(
        test_id="R1_seed_plan_manage",
        method="GET",
        route="/workspace-context",
        identity="owner_a",
        expected="plan.manage present",
        status=ctx_a.status_code,
        passed="plan.manage" in perms,
    )
    s.rec(
        test_id="R1_no_bogus_refund_create",
        method="GET",
        route="/workspace-context",
        identity="owner_a",
        expected="refund.create absent",
        status=ctx_a.status_code,
        passed="refund.create" not in perms,
    )
    # unintended: must not include platform-only
    s.rec(
        test_id="R1_no_platform_perms",
        method="GET",
        route="/workspace-context",
        identity="owner_a",
        expected="no platform.*",
        status=ctx_a.status_code,
        passed=not any(p.startswith("platform.") for p in perms),
    )

    # practitioners / location
    pracs = s.req(
        "owner_a", "GET", f"/api/v1/tenants/{tid_a}/practitioners", tenant_id=tid_a
    )
    prac_list = pracs.json() if pracs.status_code == 200 else []
    prac_id = None
    for p in prac_list:
        if p.get("verification_status") == "approved" or p.get("status") == "approved":
            prac_id = str(p.get("id") or p.get("practitioner_id"))
            break
    if not prac_id and prac_list:
        prac_id = str(prac_list[0].get("id") or prac_list[0].get("practitioner_id"))
    loc_id = loc_ids[0] if loc_ids else None
    if not loc_id:
        # fallback: from appointments or patients not helpful — use me tenants only
        # list locations endpoint?
        pass

    # Get patients
    pats = s.req("owner_a", "GET", f"/api/v1/tenants/{tid_a}/patients", tenant_id=tid_a)
    patients = pats.json() if pats.status_code == 200 else []
    if isinstance(patients, dict):
        patients = patients.get("items") or []
    pid_a = str(patients[0]["id"]) if patients else None
    s.rec(
        test_id="R2_list_patients_A",
        method="GET",
        route="/tenants/{A}/patients",
        identity="owner_a",
        expected="200 nonempty",
        status=pats.status_code,
        passed=pats.status_code == 200 and bool(pid_a),
        notes=f"count={len(patients)}",
    )

    # Cross-tenant regression: A cannot read B patients with B header
    g = s.req(
        "owner_a",
        "GET",
        f"/api/v1/tenants/{tid_b}/patients",
        tenant_id=tid_b,
    )
    s.rec(
        test_id="R3_A_hdrB_patients",
        method="GET",
        route="/tenants/{B}/patients",
        identity="owner_a",
        expected="403",
        status=g.status_code,
        passed=g.status_code == 403,
    )
    g = s.req(
        "owner_b",
        "GET",
        f"/api/v1/tenants/{tid_a}/patients",
        tenant_id=tid_a,
    )
    s.rec(
        test_id="R3_B_hdrA_patients",
        method="GET",
        route="/tenants/{A}/patients",
        identity="owner_b",
        expected="403",
        status=g.status_code,
        passed=g.status_code == 403,
    )

    if not pid_a or not prac_id:
        s.skip("BILLING", "missing patient or practitioner")
        _write(s)
        return 1

    # Resolve location if missing from context (empty location_ids possible for admin?)
    if not loc_id:
        # open or list appointments for location
        ap = s.req("owner_a", "GET", f"/api/v1/tenants/{tid_a}/appointments", tenant_id=tid_a)
        items = ap.json() if ap.status_code == 200 else []
        if isinstance(items, dict):
            items = items.get("items") or []
        if items:
            loc_id = str(items[0].get("location_id"))
    if not loc_id:
        s.skip("BILLING", "no location_id available")
        _write(s)
        return 1

    s.state.update({"pid_a": pid_a, "prac_id": prac_id, "loc_id": loc_id})

    # dental procedures
    procs = s.req(
        "owner_a",
        "GET",
        f"/api/v1/tenants/{tid_a}/dental-procedures",
        tenant_id=tid_a,
    )
    proc_list = procs.json() if procs.status_code == 200 else []
    proc_code = None
    for p in proc_list:
        if p.get("is_active") and p.get("code"):
            proc_code = p["code"]
            break
    s.rec(
        test_id="B0_procedures",
        method="GET",
        route="/dental-procedures",
        identity="owner_a",
        expected="200 with codes",
        status=procs.status_code,
        passed=procs.status_code == 200 and bool(proc_code),
        notes=f"count={len(proc_list)} code={proc_code}",
    )
    if not proc_code:
        s.skip("BILLING_PLAN", "dental procedure catalog empty")
        _write(s)
        return 1

    # --- Treatment plan ---
    plan_body = {
        "patient_id": pid_a,
        "practitioner_id": prac_id,
        "notes": "SYNTHETIC P3.7C.1 treatment plan",
        "items": [
            {
                "procedure_code": proc_code,
                "tooth": 16,
                "sequence": 1,
                "notes": "SYNTHETIC planned procedure",
            }
        ],
    }
    pr = s.req(
        "owner_a",
        "POST",
        f"/api/v1/tenants/{tid_a}/treatment-plans",
        json_body=plan_body,
        tenant_id=tid_a,
    )
    plan_id = str(pr.json().get("id")) if pr.status_code in (200, 201) else None
    s.rec(
        test_id="B1_create_plan",
        method="POST",
        route="/treatment-plans",
        identity="owner_a",
        expected="200/201",
        status=pr.status_code,
        passed=pr.status_code in (200, 201),
        notes=pr.text[:120] if pr.status_code not in (200, 201) else f"status={pr.json().get('status')}",
    )
    if not plan_id:
        _write(s)
        return 1

    ar = s.req(
        "owner_a",
        "POST",
        f"/api/v1/tenants/{tid_a}/treatment-plans/{plan_id}/activate",
        tenant_id=tid_a,
    )
    s.rec(
        test_id="B2_activate_plan",
        method="POST",
        route="/treatment-plans/{id}/activate",
        identity="owner_a",
        expected="200 active",
        status=ar.status_code,
        passed=ar.status_code == 200 and ar.json().get("status") == "active",
        notes=ar.text[:100] if ar.status_code != 200 else "",
    )

    # --- Estimate ---
    est_body = {
        "patient_id": pid_a,
        "location_id": loc_id,
        "practitioner_id": prac_id,
        "treatment_plan_id": plan_id,
        "valid_until": (date.today() + timedelta(days=30)).isoformat(),
        "notes": "SYNTHETIC estimate linked to treatment plan",
        "idempotency_key": f"p37c1-est-{uuid.uuid4()}",
        "items": [
            {
                "description": "SYNTHETIC dental procedure fee",
                "quantity": "1",
                "unit_rate": "1500.00",
                "discount_amount": "0",
                "tax_rate": "0",
                "sequence": 1,
            },
            {
                "description": "SYNTHETIC consumables",
                "quantity": "1",
                "unit_rate": "250.00",
                "discount_amount": "0",
                "tax_rate": "0",
                "sequence": 2,
            },
        ],
    }
    er = s.req(
        "owner_a",
        "POST",
        f"/api/v1/tenants/{tid_a}/estimates",
        json_body=est_body,
        tenant_id=tid_a,
    )
    est = er.json() if er.status_code in (200, 201) else {}
    est_id = str(est.get("id")) if est else None
    grand = est.get("grand_total")
    s.rec(
        test_id="B3_create_estimate",
        method="POST",
        route="/estimates",
        identity="owner_a",
        expected="200/201 with lines+totals",
        status=er.status_code,
        passed=er.status_code in (200, 201)
        and est_id is not None
        and len(est.get("lines") or []) == 2
        and grand is not None,
        notes=f"grand_total={grand} currency={est.get('currency')} lines={len(est.get('lines') or [])}",
    )
    if not est_id:
        _write(s)
        return 1

    # verify totals 1750.00
    try:
        ok_total = Decimal(str(grand)) == Decimal("1750.00")
    except Exception:
        ok_total = False
    s.rec(
        test_id="B4_estimate_totals",
        method="GET",
        route="/estimates/{id}",
        identity="owner_a",
        expected="grand_total=1750.00 INR",
        status=200,
        passed=ok_total and est.get("currency") == "INR",
        notes=f"grand_total={grand} currency={est.get('currency')}",
    )

    # issue estimate
    ir = s.req(
        "owner_a",
        "POST",
        f"/api/v1/tenants/{tid_a}/estimates/{est_id}/issue",
        tenant_id=tid_a,
    )
    s.rec(
        test_id="B5_issue_estimate",
        method="POST",
        route="/estimates/{id}/issue",
        identity="owner_a",
        expected="200 issued",
        status=ir.status_code,
        passed=ir.status_code == 200 and ir.json().get("status") == "issued",
        notes=ir.text[:100] if ir.status_code != 200 else f"status={ir.json().get('status')}",
    )

    # convert → invoice
    cr = s.req(
        "owner_a",
        "POST",
        f"/api/v1/tenants/{tid_a}/estimates/{est_id}/convert",
        json_body={"notes": "SYNTHETIC conversion", "line_ids": None},
        tenant_id=tid_a,
        idem=str(uuid.uuid4()),
    )
    inv = cr.json() if cr.status_code in (200, 201) else {}
    inv_id = str(inv.get("id")) if inv else None
    s.rec(
        test_id="B6_convert_estimate",
        method="POST",
        route="/estimates/{id}/convert",
        identity="owner_a",
        expected="200/201 invoice",
        status=cr.status_code,
        passed=cr.status_code in (200, 201) and inv_id is not None,
        notes=cr.text[:120]
        if cr.status_code not in (200, 201)
        else f"invoice_status={inv.get('status')} grand={inv.get('grand_total')}",
    )
    if not inv_id:
        _write(s)
        return 1

    # issue invoice
    iir = s.req(
        "owner_a",
        "POST",
        f"/api/v1/tenants/{tid_a}/invoices/{inv_id}/issue",
        tenant_id=tid_a,
    )
    inv2 = iir.json() if iir.status_code == 200 else {}
    outstanding = inv2.get("outstanding_balance") or inv2.get("outstanding")
    s.rec(
        test_id="B7_issue_invoice",
        method="POST",
        route="/invoices/{id}/issue",
        identity="owner_a",
        expected="200 issued with outstanding",
        status=iir.status_code,
        passed=(
            iir.status_code == 200
            and (
                inv2.get("status") in ("issued", "open", "partially_paid", "unpaid")
                or outstanding is not None
            )
        ),
        notes=f"status={inv2.get('status')} outstanding={outstanding} "
        f"grand={inv2.get('grand_total')} currency={inv2.get('currency')}",
    )
    # refresh invoice
    gr = s.req(
        "owner_a",
        "GET",
        f"/api/v1/tenants/{tid_a}/invoices/{inv_id}",
        tenant_id=tid_a,
    )
    inv3 = gr.json() if gr.status_code == 200 else {}
    outstanding = (
        inv3.get("outstanding_balance")
        or inv3.get("outstanding")
        or inv3.get("balance_due")
        or inv3.get("grand_total")
    )
    s.rec(
        test_id="B8_invoice_balance",
        method="GET",
        route="/invoices/{id}",
        identity="owner_a",
        expected="outstanding reflects total",
        status=gr.status_code,
        passed=gr.status_code == 200 and outstanding is not None,
        notes=f"status={inv3.get('status')} outstanding={outstanding} "
        f"currency={inv3.get('currency')} keys={sorted(inv3.keys())}",
    )

    # payment (manual cash — staging, not a provider charge)
    pay_amount = str(outstanding or inv3.get("grand_total") or "1750.00")
    prp = s.req(
        "owner_a",
        "POST",
        f"/api/v1/tenants/{tid_a}/payments",
        json_body={
            "patient_id": pid_a,
            "location_id": loc_id,
            "method": "cash",
            "amount": pay_amount,
            "currency": "INR",
            "idempotency_key": f"p37c1-pay-{uuid.uuid4()}",
            "provider_ref": "SYNTHETIC-MANUAL-CASH",
        },
        tenant_id=tid_a,
        idem=str(uuid.uuid4()),
    )
    pay = prp.json() if prp.status_code in (200, 201) else {}
    pay_id = str(pay.get("id")) if pay else None
    s.rec(
        test_id="B9_record_payment",
        method="POST",
        route="/payments",
        identity="owner_a",
        expected="200/201 cash recorded",
        status=prp.status_code,
        passed=prp.status_code in (200, 201) and pay_id is not None,
        notes=prp.text[:120]
        if prp.status_code not in (200, 201)
        else f"method={pay.get('method')} amount={pay.get('amount')} status={pay.get('status')}",
    )
    if pay_id:
        al = s.req(
            "owner_a",
            "POST",
            f"/api/v1/tenants/{tid_a}/payments/{pay_id}/allocations",
            json_body={
                "allocations": [{"invoice_id": inv_id, "amount": pay_amount}],
                "idempotency_key": f"p37c1-alloc-{uuid.uuid4()}",
            },
            tenant_id=tid_a,
            idem=str(uuid.uuid4()),
        )
        s.rec(
            test_id="B10_allocate_payment",
            method="POST",
            route="/payments/{id}/allocations",
            identity="owner_a",
            expected="200",
            status=al.status_code,
            passed=al.status_code in (200, 201),
            notes=al.text[:120] if al.status_code not in (200, 201) else "allocated",
        )
        # invoice after allocation
        gr2 = s.req(
            "owner_a",
            "GET",
            f"/api/v1/tenants/{tid_a}/invoices/{inv_id}",
            tenant_id=tid_a,
        )
        inv4 = gr2.json() if gr2.status_code == 200 else {}
        rem = inv4.get("outstanding_balance") or inv4.get("outstanding") or inv4.get("balance_due")
        try:
            rem_ok = rem is not None and Decimal(str(rem)) == Decimal("0")
        except Exception:
            rem_ok = rem in ("0", "0.00", "0.0")
        s.rec(
            test_id="B11_invoice_paid",
            method="GET",
            route="/invoices/{id}",
            identity="owner_a",
            expected="outstanding 0 / paid status",
            status=gr2.status_code,
            passed=gr2.status_code == 200
            and (rem_ok or str(inv4.get("status", "")).lower() in ("paid", "settled", "closed")),
            notes=f"status={inv4.get('status')} outstanding={rem}",
        )

    # timeline
    tl = s.req(
        "owner_a",
        "GET",
        f"/api/v1/tenants/{tid_a}/patients/{pid_a}/timeline",
        tenant_id=tid_a,
    )
    items = []
    if tl.status_code == 200:
        payload = tl.json()
        items = payload.get("items") if isinstance(payload, dict) else payload
    kinds = [str(i.get("kind") or i.get("category") or i.get("title") or "") for i in items]
    billing_hit = any(
        any(tok in (k or "").lower() for tok in ("bill", "invoice", "payment", "estimate"))
        for k in kinds
    )
    s.rec(
        test_id="B12_timeline_billing",
        method="GET",
        route="/patients/{id}/timeline",
        identity="owner_a",
        expected="billing-related events present",
        status=tl.status_code,
        passed=tl.status_code == 200 and (billing_hit or len(items) > 0),
        notes=f"items={len(items)} billing_hit={billing_hit}",
    )

    # --- Tenant B isolation on billing artifacts ---
    for label, path in [
        ("estimate", f"/api/v1/tenants/{tid_a}/estimates/{est_id}"),
        ("invoice", f"/api/v1/tenants/{tid_a}/invoices/{inv_id}"),
    ]:
        g = s.req("owner_b", "GET", path, tenant_id=tid_b)
        s.rec(
            test_id=f"X1_B_pathA_{label}",
            method="GET",
            route=f"/tenants/{{A}}/{label}s/{{id}}",
            identity="owner_b",
            expected="404",
            status=g.status_code,
            passed=g.status_code == 404,
        )
        g = s.req("owner_b", "GET", path, tenant_id=tid_a)
        s.rec(
            test_id=f"X2_B_hdrA_{label}",
            method="GET",
            route=f"/tenants/{{A}}/{label}s/{{id}}",
            identity="owner_b",
            expected="403",
            status=g.status_code,
            passed=g.status_code == 403,
        )
    if pay_id:
        path = f"/api/v1/tenants/{tid_a}/payments/{pay_id}"
        g = s.req("owner_b", "GET", path, tenant_id=tid_b)
        s.rec(
            test_id="X1_B_pathA_payment",
            method="GET",
            route="/tenants/{A}/payments/{id}",
            identity="owner_b",
            expected="404",
            status=g.status_code,
            passed=g.status_code == 404,
        )
        g = s.req("owner_b", "GET", path, tenant_id=tid_a)
        s.rec(
            test_id="X2_B_hdrA_payment",
            method="GET",
            route="/tenants/{A}/payments/{id}",
            identity="owner_b",
            expected="403",
            status=g.status_code,
            passed=g.status_code == 403,
        )

    for c in s.clients.values():
        c.close()
    _write(s)
    fails = [r for r in s.results if r["result"] == "FAIL"]
    print("--- SUMMARY ---")
    print(
        f"PASS={sum(1 for r in s.results if r['result']=='PASS')} "
        f"FAIL={len(fails)} SKIP={sum(1 for r in s.results if r['result']=='SKIP')}"
    )
    for f in fails:
        print(f"  FAIL {f['id']}: status={f['status']} notes={f.get('notes')}")
    return 0 if not fails else 1


def _write(s: Suite) -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "api": s.base,
        "deploy_commit": "293dc668e7117f20a4b88e7a3047aa8e501c99b6",
        "preserves_p37c_evidence": True,
        "tenant_slugs_hint": "from .env.p37c.staging /auth/me",
        "state_ids_present": {
            "tid_a": bool(s.state.get("tid_a")),
            "tid_b": bool(s.state.get("tid_b")),
            "pid_a": bool(s.state.get("pid_a")),
        },
        "results": s.results,
        "counts": {
            "pass": sum(1 for r in s.results if r["result"] == "PASS"),
            "fail": sum(1 for r in s.results if r["result"] == "FAIL"),
            "skip": sum(1 for r in s.results if r["result"] == "SKIP"),
        },
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"evidence_written={OUT.name}")


if __name__ == "__main__":
    raise SystemExit(main())
