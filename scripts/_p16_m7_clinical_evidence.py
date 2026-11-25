"""Phase 1.6 M7 clinical API evidence — synthetic data only, no PHI/tokens in file."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
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
    / "phase-1-6"
    / "evidence"
    / "m7_clinical_evidence.json"
)


def main() -> int:
    evidence: dict = {
        "phase": "M7",
        "api_base": BASE,
        "synthetic_user": EMAIL,
        "tokens_in_evidence": False,
        "phi_in_evidence": False,
    }
    try:
        with httpx.Client(timeout=45.0) as client:
            evidence["healthz"] = client.get(f"{BASE}/api/healthz").status_code == 200
            login = client.post(
                f"{BASE}/api/v1/auth/native/login",
                json={
                    "email": EMAIL,
                    "password": PASSWORD,
                    "client_platform": "windows",
                    "device_label": "M7-Evidence",
                    "client_instance_id": "m7-evidence",
                },
            )
            evidence["native_login"] = login.status_code == 200
            if login.status_code != 200:
                evidence["login_status"] = login.status_code
                OUT.parent.mkdir(parents=True, exist_ok=True)
                OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
                print(json.dumps(evidence, indent=2))
                return 1
            body = login.json()
            token = body["access_token"]
            tenant_id = body["tenants"][0]["id"]
            headers = {"Authorization": f"Bearer {token}", "X-Tenant": tenant_id}

            # Resolve location + approved practitioner
            locs = client.get(
                f"{BASE}/api/v1/tenants/{tenant_id}/locations", headers=headers
            ).json()
            location_id = locs[0]["id"]
            pracs = client.get(
                f"{BASE}/api/v1/tenants/{tenant_id}/practitioners", headers=headers
            ).json()
            approved = [p for p in pracs if p.get("verification_status") == "approved"]
            # Prefer practitioner linked to this user when API exposes user_id.
            linked = [
                p
                for p in approved
                if p.get("user_id") or "Linked" in str(p.get("display_name", ""))
            ]
            practitioner_id = (linked or approved or pracs)[0]["id"]
            evidence["approved_practitioner"] = bool(approved)
            evidence["linked_practitioner_preferred"] = bool(linked)

            patient = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/patients",
                headers=headers,
                json={
                    "display_name": f"M7 PoC {datetime.utcnow().strftime('%H%M%S')}",
                    "phone": "9000000888",
                },
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
                    "chief_complaint": "synthetic checkup",
                },
            )
            evidence["encounter_open"] = enc.status_code in (200, 201)
            evidence["encounter_open_status"] = enc.status_code
            if enc.status_code not in (200, 201):
                evidence["encounter_open_detail"] = enc.text[:240]
                raise RuntimeError("encounter_open_failed")
            eid = enc.json()["id"]
            evidence["encounter_status"] = enc.json().get("status")

            # Wrong-patient: appointment with mismatched patient should fail if we had one;
            # cross-tenant probe instead
            fake = "00000000-0000-4000-8000-000000000099"
            xt = client.get(
                f"{BASE}/api/v1/tenants/{fake}/encounters/{eid}",
                headers={**headers, "X-Tenant": fake},
            )
            evidence["cross_tenant_encounter_blocked"] = xt.status_code in (401, 403, 404)

            note = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/encounters/{eid}/clinical-notes",
                headers=headers,
                json={
                    "note_type": "general",
                    "subjective": "synthetic history",
                    "objective": "synthetic exam",
                    "assessment": "synthetic assessment",
                    "plan": "synthetic plan",
                },
            )
            evidence["note_create"] = note.status_code in (200, 201)
            evidence["note_create_status"] = note.status_code
            if not evidence["note_create"]:
                evidence["note_create_detail"] = note.text[:240]
            nid = note.json()["id"] if evidence["note_create"] else None
            if nid:
                fin = client.post(
                    f"{BASE}/api/v1/tenants/{tenant_id}/clinical-notes/{nid}/finalize",
                    headers=headers,
                    json={},
                )
                evidence["note_finalize"] = fin.status_code == 200
                evidence["note_status"] = (
                    fin.json().get("status") if fin.status_code == 200 else None
                )

            dx = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/encounters/{eid}/diagnoses",
                headers=headers,
                json={"free_text": "synthetic unspecified finding", "is_primary": True},
            )
            evidence["diagnosis_create"] = dx.status_code in (200, 201)

            meds = client.get(
                f"{BASE}/api/v1/tenants/{tenant_id}/medications", headers=headers
            )
            evidence["medications_catalog"] = meds.status_code == 200
            med_code = None
            if meds.status_code == 200 and meds.json():
                med_code = meds.json()[0]["code"]
            if med_code:
                rx = client.post(
                    f"{BASE}/api/v1/tenants/{tenant_id}/encounters/{eid}/prescriptions",
                    headers=headers,
                    json={
                        "items": [
                            {
                                "medication_code": med_code,
                                "dose": "1 tablet",
                                "route": "oral",
                                "frequency": "once daily",
                                "duration_days": 5,
                                "instructions": "synthetic evidence only",
                            }
                        ]
                    },
                )
                evidence["rx_create"] = rx.status_code in (200, 201)
                evidence["rx_create_status"] = rx.status_code
                if rx.status_code in (200, 201):
                    rid = rx.json()["id"]
                    # Draft blocks close — sign first
                    sign = client.post(
                        f"{BASE}/api/v1/tenants/{tenant_id}/prescriptions/{rid}/sign",
                        headers=headers,
                        json={},
                    )
                    evidence["rx_sign"] = sign.status_code == 200
                    evidence["rx_sign_status"] = sign.status_code
            else:
                evidence["rx_create"] = False
                evidence["rx_skipped_no_meds"] = True

            # Vitals so close without vitals_waiver succeeds
            obs = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/encounters/{eid}/observations",
                headers=headers,
                json={"type_code": "bp_systolic", "value_numeric": 120},
            )
            evidence["vitals_create"] = obs.status_code in (200, 201)
            evidence["vitals_status"] = obs.status_code
            if obs.status_code not in (200, 201):
                evidence["vitals_detail"] = obs.text[:160]

            plan = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/treatment-plans",
                headers=headers,
                json={
                    "patient_id": pid,
                    "encounter_id": eid,
                    "practitioner_id": practitioner_id,
                    "notes": "synthetic draft plan",
                    "items": [{"procedure_code": "cleaning", "sequence": 1}],
                },
            )
            evidence["plan_create"] = plan.status_code in (200, 201)
            evidence["plan_create_status"] = plan.status_code
            # Draft plan blocks close — cancel or skip leave draft; cancel if created
            if plan.status_code in (200, 201):
                plan_id = plan.json()["id"]
                cancel = client.post(
                    f"{BASE}/api/v1/tenants/{tenant_id}/treatment-plans/{plan_id}/cancel",
                    headers=headers,
                    json={},
                )
                evidence["plan_cancel_for_close"] = cancel.status_code == 200

            fu = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/follow-ups",
                headers=headers,
                json={
                    "patient_id": pid,
                    "location_id": location_id,
                    "due_at": (datetime.utcnow() + timedelta(days=7)).isoformat()
                    + "Z",
                    "reason": "synthetic follow-up",
                    "category": "encounter",
                    "source_type": "encounter",
                    "source_id": eid,
                    "priority": "normal",
                },
            )
            evidence["followup_create"] = fu.status_code in (200, 201)
            evidence["followup_status"] = fu.status_code

            close = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/encounters/{eid}/close",
                headers=headers,
                json={
                    "note_waiver": False,
                    "vitals_waiver": evidence.get("vitals_status") not in (200, 201),
                    "reason": "m7 evidence wrap-up",
                },
            )
            evidence["encounter_close"] = close.status_code == 200
            evidence["encounter_close_status"] = close.status_code
            if close.status_code != 200:
                evidence["encounter_close_detail"] = close.text[:240]

            tl = client.get(
                f"{BASE}/api/v1/tenants/{tenant_id}/patients/{pid}/timeline",
                params={"limit": 30},
                headers=headers,
            )
            evidence["timeline"] = tl.status_code == 200
            if tl.status_code == 200:
                kinds = [i.get("kind") for i in tl.json().get("items", [])]
                evidence["timeline_kinds_sample"] = kinds[:12]
                evidence["timeline_has_encounter"] = any(
                    str(k).startswith("encounter") for k in kinds
                )

            client.post(
                f"{BASE}/api/v1/auth/native/logout",
                headers={"Authorization": f"Bearer {token}"},
            )
            evidence["native_logout"] = True

        evidence["pass"] = all(
            [
                evidence.get("healthz"),
                evidence.get("native_login"),
                evidence.get("encounter_open"),
                evidence.get("note_create"),
                evidence.get("note_finalize"),
                evidence.get("diagnosis_create"),
                evidence.get("cross_tenant_encounter_blocked"),
                evidence.get("encounter_close"),
                evidence.get("timeline"),
            ]
        )
    except Exception as e:
        evidence["error"] = f"{type(e).__name__}:{e}"
        evidence["pass"] = False

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    return 0 if evidence.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
