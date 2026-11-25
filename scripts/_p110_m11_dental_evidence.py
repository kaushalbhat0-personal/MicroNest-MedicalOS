"""Phase 1.10 M11 dental evidence — synthetic clinical IDs only; no PHI dumps."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
EMAIL = "desktop.poc@example.com"
PASSWORD = "Desktop-PoC-Only-99zz"
BASE = os.environ.get("API_PUBLIC_URL", "http://localhost:8000").rstrip("/")
OUT = (
    ROOT
    / "docs"
    / "architecture"
    / "desktop-client"
    / "phase-1-10"
    / "evidence"
    / "m11_dental_evidence.json"
)


def _ok(r: httpx.Response) -> bool:
    return 200 <= r.status_code < 300


def main() -> int:
    evidence: dict = {
        "phase": "M11",
        "api_base": BASE,
        "synthetic_user": EMAIL,
        "tokens_in_evidence": False,
        "phi_in_evidence": False,
        "dentist_validation": "PENDING",
    }
    try:
        with httpx.Client(timeout=60.0) as client:
            evidence["healthz"] = client.get(f"{BASE}/api/healthz").status_code == 200
            login = client.post(
                f"{BASE}/api/v1/auth/native/login",
                json={
                    "email": EMAIL,
                    "password": PASSWORD,
                    "client_platform": "windows",
                    "device_label": "M11-Evidence",
                    "client_instance_id": "m11-evidence",
                },
            )
            evidence["native_login"] = login.status_code == 200
            if login.status_code != 200:
                evidence["login_status"] = login.status_code
                OUT.parent.mkdir(parents=True, exist_ok=True)
                OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
                print(json.dumps(evidence, indent=2))
                return 1

            token = login.json()["access_token"]
            tenant_id = login.json()["tenants"][0]["id"]
            headers = {"Authorization": f"Bearer {token}", "X-Tenant": tenant_id}

            fake = str(uuid.uuid4())
            xt = client.get(
                f"{BASE}/api/v1/tenants/{fake}/dental-conditions",
                headers={**headers, "X-Tenant": fake},
            )
            evidence["cross_tenant_dental_denied"] = xt.status_code in (401, 403, 404)

            locs = client.get(
                f"{BASE}/api/v1/tenants/{tenant_id}/locations", headers=headers
            ).json()
            location_id = locs[0]["id"]

            # Linked practitioner for clinical writes
            me = client.get(f"{BASE}/api/v1/auth/me", headers=headers).json()
            user_id = me["id"]
            pracs = client.get(
                f"{BASE}/api/v1/tenants/{tenant_id}/practitioners", headers=headers
            ).json()
            practitioner_id = None
            for p in pracs:
                if p.get("user_id") == user_id or p.get("verification_status") == "approved":
                    practitioner_id = p["id"]
                    if p.get("user_id") == user_id:
                        break
            if not practitioner_id and pracs:
                practitioner_id = pracs[0]["id"]
            evidence["practitioner_resolved"] = bool(practitioner_id)

            patient = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/patients",
                headers=headers,
                json={"display_name": f"M11 Dental PoC {uuid.uuid4().hex[:6]}"},
            ).json()
            pid = patient["id"]
            evidence["patient_create"] = True

            enc = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/encounters",
                headers=headers,
                json={
                    "patient_id": pid,
                    "practitioner_id": practitioner_id,
                    "location_id": location_id,
                },
            )
            evidence["encounter_open"] = _ok(enc)
            if not _ok(enc):
                evidence["encounter_error"] = enc.status_code
                evidence["pass"] = False
                OUT.parent.mkdir(parents=True, exist_ok=True)
                OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
                print(json.dumps(evidence, indent=2))
                return 1
            eid = enc.json()["id"]

            conds = client.get(
                f"{BASE}/api/v1/tenants/{tenant_id}/dental-conditions", headers=headers
            )
            evidence["conditions_list"] = conds.status_code == 200
            code = "caries"
            if conds.status_code == 200 and conds.json():
                code = conds.json()[0]["code"]

            # Bad tooth rejected
            bad = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/encounters/{eid}/tooth-findings",
                headers=headers,
                json={"tooth": 99, "condition_code": code},
            )
            evidence["invalid_tooth_rejected"] = bad.status_code in (400, 422)

            # Primary deferred
            primary = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/encounters/{eid}/tooth-findings",
                headers=headers,
                json={"tooth": 51, "condition_code": code},
            )
            evidence["primary_dentition_rejected"] = primary.status_code in (400, 422)

            finding = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/encounters/{eid}/tooth-findings",
                headers=headers,
                json={
                    "tooth": 16,
                    "condition_code": code,
                    "surfaces": ["mesial", "occlusal"],
                },
            )
            evidence["finding_record"] = _ok(finding)
            fid = finding.json()["id"] if _ok(finding) else None

            listed = client.get(
                f"{BASE}/api/v1/tenants/{tenant_id}/encounters/{eid}/tooth-findings",
                headers=headers,
            )
            evidence["findings_list"] = listed.status_code == 200

            if fid:
                resolved = client.post(
                    f"{BASE}/api/v1/tenants/{tenant_id}/tooth-findings/{fid}/resolve",
                    headers=headers,
                    json={},
                )
                evidence["finding_resolve"] = _ok(resolved)

            procs = client.get(
                f"{BASE}/api/v1/tenants/{tenant_id}/dental-procedures", headers=headers
            )
            evidence["procedure_catalog"] = procs.status_code == 200
            proc_code = "filling"
            if procs.status_code == 200 and procs.json():
                proc_code = procs.json()[0]["code"]

            plan = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/treatment-plans",
                headers=headers,
                json={
                    "patient_id": pid,
                    "encounter_id": eid,
                    "practitioner_id": practitioner_id,
                    "notes": "M11 synthetic plan",
                    "items": [{"procedure_code": proc_code, "tooth": 16, "sequence": 1}],
                },
            )
            evidence["plan_create"] = _ok(plan)
            plan_id = plan.json()["id"] if _ok(plan) else None

            if plan_id:
                act = client.post(
                    f"{BASE}/api/v1/tenants/{tenant_id}/treatment-plans/{plan_id}/activate",
                    headers=headers,
                    json={},
                )
                evidence["plan_activate_without_consent"] = _ok(act)

            # Procedure without consent → in_progress denied
            rec = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/encounters/{eid}/procedure-records",
                headers=headers,
                json={"procedure_code": proc_code, "tooth": 16},
            )
            evidence["procedure_record_create"] = _ok(rec)
            rid = rec.json()["id"] if _ok(rec) else None

            if rid:
                denied = client.post(
                    f"{BASE}/api/v1/tenants/{tenant_id}/procedure-records/{rid}/status",
                    headers=headers,
                    json={"status": "in_progress"},
                )
                evidence["procedure_in_progress_without_consent_denied"] = (
                    denied.status_code == 403
                )

                consent = client.post(
                    f"{BASE}/api/v1/tenants/{tenant_id}/consents",
                    headers=headers,
                    json={
                        "procedure_record_id": rid,
                        "consenter_name": "M11 Synthetic Consenter",
                    },
                )
                evidence["consent_create"] = _ok(consent)
                cid = consent.json()["id"] if _ok(consent) else None
                if cid:
                    decided = client.post(
                        f"{BASE}/api/v1/tenants/{tenant_id}/consents/{cid}/decide",
                        headers=headers,
                        json={"decision": "granted"},
                    )
                    evidence["consent_grant"] = _ok(decided)

                allowed = client.post(
                    f"{BASE}/api/v1/tenants/{tenant_id}/procedure-records/{rid}/status",
                    headers=headers,
                    json={"status": "in_progress"},
                )
                evidence["procedure_in_progress_with_consent"] = _ok(allowed)

            # Gaps
            evidence["list_consents_http"] = False
            evidence["primary_dentition"] = False
            evidence["odontogram_persisted"] = False
            evidence["ai_cds"] = False

            required = [
                "finding_record",
                "invalid_tooth_rejected",
                "primary_dentition_rejected",
                "procedure_in_progress_without_consent_denied",
                "cross_tenant_dental_denied",
            ]
            evidence["pass"] = all(evidence.get(k) for k in required)
            evidence["recorded_at"] = datetime.now(timezone.utc).isoformat()

    except Exception as exc:  # noqa: BLE001
        evidence["error"] = type(exc).__name__
        evidence["pass"] = False

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    return 0 if evidence.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
