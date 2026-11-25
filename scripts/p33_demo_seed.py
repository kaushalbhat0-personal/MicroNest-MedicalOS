"""P3.3 synthetic demonstration seed via local HTTP API (dev only).

Creates labeled TEST clinic data for usability walkthrough screenshots.
Requires API running at NEXT_PUBLIC_API_URL / http://localhost:8000.

Refuses ENV preview/prod/production. Never prints passwords.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import error, request

ROOT = Path(__file__).resolve().parents[1]
_env_path = ROOT / ".env"
if _env_path.is_file():
    for line in _env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

API = (os.environ.get("NEXT_PUBLIC_API_URL") or "http://localhost:8000").rstrip("/")
EMAIL = os.environ.get("P33_DEMO_OWNER_EMAIL", "p33.demo.owner@example.com").strip()
PASSWORD = os.environ.get("P33_DEMO_OWNER_PASSWORD", "P33-Demo-Owner-12345").strip()


class Api:
    def __init__(self) -> None:
        self.cookie = ""

    def call(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        *,
        tenant: str | None = None,
        headers: dict[str, str] | None = None,
        expect: tuple[int, ...] = (200, 201, 202, 204),
    ) -> dict | list | None:
        data = None if body is None else json.dumps(body).encode()
        req = request.Request(f"{API}{path}", data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if self.cookie:
            req.add_header("Cookie", self.cookie)
        if tenant:
            req.add_header("X-Tenant", tenant)
        if headers:
            for k, v in headers.items():
                req.add_header(k, v)
        try:
            with request.urlopen(req, timeout=30) as res:
                raw_set = res.headers.get_all("Set-Cookie") or []
                parts = []
                for sc in raw_set:
                    parts.append(sc.split(";", 1)[0])
                if parts:
                    # merge cookie jar simply
                    jar = {}
                    if self.cookie:
                        for pair in self.cookie.split("; "):
                            if "=" in pair:
                                k, _, v = pair.partition("=")
                                jar[k] = v
                    for pair in parts:
                        if "=" in pair:
                            k, _, v = pair.partition("=")
                            jar[k] = v
                    self.cookie = "; ".join(f"{k}={v}" for k, v in jar.items())
                payload = res.read().decode() or "null"
                if res.status not in expect and res.status not in (200, 201, 202, 204):
                    raise RuntimeError(f"{method} {path} -> {res.status} {payload}")
                return json.loads(payload) if payload and payload != "null" else None
        except error.HTTPError as exc:
            detail = exc.read().decode()
            if exc.code in expect:
                return json.loads(detail) if detail else None
            raise RuntimeError(f"{method} {path} -> {exc.code} {detail}") from exc


def main() -> int:
    env = (os.environ.get("ENV") or "dev").lower()
    if env in ("preview", "prod", "production"):
        print("REFUSED: p33_demo_seed is for local/dev/test only", file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).strftime("%m%d%H%M")
    api = Api()

    # Health
    try:
        request.urlopen(f"{API}/api/healthz", timeout=5)
    except Exception as exc:
        print(f"BLOCKED: API unreachable at {API}: {exc}", file=sys.stderr)
        return 2

    api.call(
        "POST",
        "/api/v1/auth/signup",
        {
            "email": EMAIL,
            "password": PASSWORD,
            "display_name": "P33 DEMO Owner",
        },
        expect=(202,),
    )

    me = api.call("POST", "/api/v1/auth/login", {"email": EMAIL, "password": PASSWORD})
    assert isinstance(me, dict)
    tenants = me.get("tenants") or []
    demo = next((t for t in tenants if str(t.get("slug", "")).startswith("p33-demo")), None)

    if demo:
        tenant_id = demo["id"]
        print(f"reusing_tenant slug={demo['slug']} id={tenant_id}")
    else:
        slug = f"p33-demo-{stamp}"
        ws = api.call(
            "POST",
            "/api/v1/workspaces",
            {
                "clinic_name": f"P33 DEMO Dental Clinic {stamp}",
                "slug": slug,
                "location_name": "P33 DEMO Main Chair",
                "timezone": "Asia/Kolkata",
                "practitioner_display_name": "P33 DEMO Dr Dentist",
                "specialty_codes": ["dental"],
            },
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert isinstance(ws, dict)
        tenant_id = ws["tenant"]["id"]
        pract_id = ws["practitioner"]["id"]
        print(f"created_tenant slug={slug} id={tenant_id}")
        api.call(
            "POST",
            f"/api/v1/tenants/{tenant_id}/verification",
            {"practitioner_id": pract_id, "status": "approved"},
            tenant=tenant_id,
        )

    # Refresh me for tenant context
    me = api.call("GET", "/api/v1/auth/me")
    assert isinstance(me, dict)

    # Locations + practitioners
    locs = api.call("GET", f"/api/v1/tenants/{tenant_id}/locations", tenant=tenant_id)
    assert isinstance(locs, list) and locs
    location_id = locs[0]["id"]
    practs = api.call("GET", f"/api/v1/tenants/{tenant_id}/practitioners", tenant=tenant_id)
    if not isinstance(practs, list) or not practs:
        # alternate path
        ver = api.call("GET", f"/api/v1/tenants/{tenant_id}/verification", tenant=tenant_id)
        assert isinstance(ver, list) and ver
        pract_id = ver[0]["practitioner_id"]
        api.call(
            "POST",
            f"/api/v1/tenants/{tenant_id}/verification",
            {"practitioner_id": pract_id, "status": "approved"},
            tenant=tenant_id,
        )
    else:
        pract_id = practs[0]["id"]
        if practs[0].get("verification_status") != "approved":
            api.call(
                "POST",
                f"/api/v1/tenants/{tenant_id}/verification",
                {"practitioner_id": pract_id, "status": "approved"},
                tenant=tenant_id,
            )

    # Patient
    patients = api.call("GET", f"/api/v1/tenants/{tenant_id}/patients", tenant=tenant_id)
    patient = None
    if isinstance(patients, list):
        patient = next((p for p in patients if "P33 DEMO Patient" in p.get("display_name", "")), None)
    if patient is None:
        patient = api.call(
            "POST",
            f"/api/v1/tenants/{tenant_id}/patients",
            {"display_name": "P33 DEMO Patient Alpha", "phone": "+910000000033"},
            tenant=tenant_id,
        )
    assert isinstance(patient, dict)
    patient_id = patient["id"]

    # Appointment
    start = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    try:
        api.call(
            "POST",
            f"/api/v1/tenants/{tenant_id}/appointments",
            {
                "patient_id": patient_id,
                "practitioner_id": pract_id,
                "location_id": location_id,
                "starts_at": start,
                "duration_minutes": 30,
            },
            tenant=tenant_id,
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
    except RuntimeError as exc:
        print(f"appointment_skip={exc}")

    # Encounter
    enc = None
    try:
        enc = api.call(
            "POST",
            f"/api/v1/tenants/{tenant_id}/encounters",
            {
                "patient_id": patient_id,
                "practitioner_id": pract_id,
                "location_id": location_id,
            },
            tenant=tenant_id,
        )
    except RuntimeError as exc:
        print(f"encounter_skip={exc}")
    enc_id = enc["id"] if isinstance(enc, dict) else None

    if enc_id:
        try:
            api.call(
                "POST",
                f"/api/v1/tenants/{tenant_id}/encounters/{enc_id}/tooth-findings",
                {"tooth": 16, "condition_code": "caries"},
                tenant=tenant_id,
            )
        except RuntimeError as exc:
            # try non-tenant-prefixed
            try:
                api.call(
                    "POST",
                    f"/api/v1/encounters/{enc_id}/tooth-findings",
                    {"tooth": 16, "condition_code": "caries"},
                    tenant=tenant_id,
                )
            except RuntimeError as exc2:
                print(f"finding_skip={exc2}")

    # Treatment plan
    plan_id = None
    try:
        plan = api.call(
            "POST",
            f"/api/v1/tenants/{tenant_id}/treatment-plans",
            {
                "patient_id": patient_id,
                "practitioner_id": pract_id,
                "encounter_id": enc_id,
                "items": [{"procedure_code": "restoration", "tooth": 16}],
                "notes": "P33 DEMO synthetic plan",
            },
            tenant=tenant_id,
        )
        if isinstance(plan, dict):
            plan_id = plan.get("id")
    except RuntimeError as exc:
        print(f"plan_skip={exc}")

    # Follow-up
    try:
        api.call(
            "POST",
            f"/api/v1/tenants/{tenant_id}/follow-ups",
            {
                "patient_id": patient_id,
                "due_at": (datetime.now(timezone.utc) + timedelta(days=7)).date().isoformat(),
                "reason": "P33 DEMO synthetic follow-up",
            },
            tenant=tenant_id,
        )
    except RuntimeError as exc:
        print(f"followup_skip={exc}")

    out = {
        "api": API,
        "owner_email": EMAIL,
        "tenant_id": tenant_id,
        "patient_id": patient_id,
        "location_id": location_id,
        "practitioner_id": pract_id,
        "encounter_id": enc_id,
        "plan_id": plan_id,
    }
    print(json.dumps(out, indent=2))
    print("password_set=yes (not printed)")
    # Write machine-readable fixture for Playwright (no secrets)
    fixture = ROOT / "docs" / "ui-ux" / "screenshots" / "p33-demo-fixture.json"
    fixture.parent.mkdir(parents=True, exist_ok=True)
    fixture.write_text(json.dumps({k: v for k, v in out.items() if k != "api"}, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
