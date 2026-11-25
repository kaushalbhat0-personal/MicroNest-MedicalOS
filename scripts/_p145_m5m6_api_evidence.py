"""Phase 1.4+1.5 API evidence against local FastAPI using synthetic desktop PoC user.

Writes JSON without PHI (ids/status only). Does not print passwords to evidence file.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
EMAIL = "desktop.poc@example.com"
PASSWORD = "Desktop-PoC-Only-99zz"
BASE = os.environ.get("API_PUBLIC_URL", "http://localhost:8000").rstrip("/")
OUT = ROOT / "docs" / "architecture" / "desktop-client" / "phase-1-4-5" / "evidence" / "m5m6_api_evidence.json"


def main() -> int:
    evidence: dict = {
        "phase": "M5+M6",
        "api_base": BASE,
        "synthetic_user": EMAIL,
        "tokens_in_evidence": False,
        "phi_in_evidence": False,
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            health = client.get(f"{BASE}/api/healthz")
            evidence["healthz"] = health.status_code == 200

            login = client.post(
                f"{BASE}/api/v1/auth/native/login",
                json={
                    "email": EMAIL,
                    "password": PASSWORD,
                    "client_platform": "windows",
                    "device_label": "HealthcareOS-Desktop-M5M6",
                    "client_instance_id": "m5m6-evidence-script",
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
            headers = {
                "Authorization": f"Bearer {token}",
                "X-Tenant": tenant_id,
            }

            patients = client.get(
                f"{BASE}/api/v1/tenants/{tenant_id}/patients",
                params={"limit": 20, "q": "PoC"},
                headers=headers,
            )
            evidence["patients_list"] = patients.status_code == 200
            evidence["patients_count"] = (
                len(patients.json()) if patients.status_code == 200 else 0
            )

            create = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/patients",
                headers=headers,
                json={
                    "display_name": f"M5 PoC Patient {datetime.utcnow().strftime('%H%M%S')}",
                    "phone": "9000000999",
                },
            )
            evidence["patient_create"] = create.status_code in (200, 201)
            patient = create.json() if evidence["patient_create"] else None
            pid = patient["id"] if patient else None
            evidence["duplicate_hint_count"] = (
                len(patient.get("potential_duplicates") or []) if patient else 0
            )

            if pid:
                overview = client.get(
                    f"{BASE}/api/v1/tenants/{tenant_id}/patients/{pid}/overview",
                    headers=headers,
                )
                evidence["patient_overview"] = overview.status_code == 200
                timeline = client.get(
                    f"{BASE}/api/v1/tenants/{tenant_id}/patients/{pid}/timeline",
                    params={"limit": 20},
                    headers=headers,
                )
                evidence["patient_timeline"] = timeline.status_code == 200
                evidence["timeline_items"] = (
                    len(timeline.json().get("items", []))
                    if timeline.status_code == 200
                    else 0
                )
                patch = client.patch(
                    f"{BASE}/api/v1/tenants/{tenant_id}/patients/{pid}",
                    headers=headers,
                    json={"emergency_contact_name": "PoC Contact"},
                )
                evidence["patient_patch"] = patch.status_code == 200

            locs = client.get(
                f"{BASE}/api/v1/tenants/{tenant_id}/locations", headers=headers
            )
            evidence["locations"] = locs.status_code == 200
            location_id = locs.json()[0]["id"] if locs.status_code == 200 and locs.json() else None

            pracs = client.get(
                f"{BASE}/api/v1/tenants/{tenant_id}/practitioners", headers=headers
            )
            evidence["practitioners"] = pracs.status_code == 200
            practitioner_id = None
            if pracs.status_code == 200 and pracs.json():
                rows = pracs.json()
                preferred = next(
                    (
                        p
                        for p in rows
                        if "Desktop PoC" in str(p.get("display_name", ""))
                    ),
                    None,
                )
                practitioner_id = (preferred or rows[0])["id"]
                evidence["practitioner_selected"] = practitioner_id[:8]

            day = date.today().isoformat()
            if location_id and practitioner_id:
                avail = client.get(
                    f"{BASE}/api/v1/tenants/{tenant_id}/availability",
                    params={
                        "practitioner_id": practitioner_id,
                        "location_id": location_id,
                        "day": day,
                    },
                    headers=headers,
                )
                evidence["availability"] = avail.status_code == 200
                slots = avail.json().get("slots", []) if avail.status_code == 200 else []
                evidence["availability_slots"] = len(slots)

                start = None
                if slots:
                    start = slots[0]["start_at"]
                else:
                    # Future wall-clock start when no published slots (still server-validated).
                    tomorrow = (date.today() + timedelta(days=1)).isoformat()
                    start = f"{tomorrow}T10:30:00"

                if pid:
                    book = client.post(
                        f"{BASE}/api/v1/tenants/{tenant_id}/appointments",
                        headers=headers,
                        json={
                            "patient_id": pid,
                            "practitioner_id": practitioner_id,
                            "location_id": location_id,
                            "start": start,
                            "duration_minutes": 30,
                            "walk_in": False,
                        },
                    )
                    evidence["appointment_create"] = book.status_code in (200, 201, 409)
                    evidence["appointment_create_status"] = book.status_code
                    if book.status_code not in (200, 201, 409):
                        evidence["appointment_create_detail"] = str(book.text)[:240]
                    appt = book.json() if book.status_code in (200, 201) else None
                    aid = appt["id"] if appt else None

                    walk = client.post(
                        f"{BASE}/api/v1/tenants/{tenant_id}/appointments",
                        headers=headers,
                        json={
                            "patient_id": pid,
                            "practitioner_id": practitioner_id,
                            "location_id": location_id,
                            "start": (datetime.now() + timedelta(minutes=5)).strftime(
                                "%Y-%m-%dT%H:%M:%S"
                            ),
                            "duration_minutes": 20,
                            "walk_in": True,
                        },
                    )
                    evidence["walk_in"] = walk.status_code in (200, 201, 409)
                    evidence["walk_in_status"] = walk.status_code
                    if walk.status_code in (200, 201):
                        evidence["walk_in_initial_status"] = walk.json().get("status")
                        if aid is None:
                            aid = walk.json().get("id")

                    if aid:
                        # For walk-in already checked_in, duplicate check-in probes idempotency.
                        checkin = client.post(
                            f"{BASE}/api/v1/tenants/{tenant_id}/appointments/{aid}/status",
                            headers=headers,
                            json={"status": "checked_in"},
                        )
                        evidence["check_in"] = checkin.status_code == 200
                        if checkin.status_code == 200:
                            evidence["queue_token_assigned"] = (
                                checkin.json().get("queue_token") is not None
                            )
                        dup = client.post(
                            f"{BASE}/api/v1/tenants/{tenant_id}/appointments/{aid}/status",
                            headers=headers,
                            json={"status": "checked_in"},
                        )
                        evidence["duplicate_check_in_status"] = dup.status_code

                queue = client.get(
                    f"{BASE}/api/v1/tenants/{tenant_id}/locations/{location_id}/reception-queue",
                    params={"day": day},
                    headers=headers,
                )
                evidence["reception_queue"] = queue.status_code == 200
                if queue.status_code == 200:
                    q = queue.json()
                    evidence["queue_bucket_counts"] = {
                        k: len(q.get(k, []))
                        for k in (
                            "waiting",
                            "checked_in",
                            "completed",
                            "no_show",
                            "cancelled",
                        )
                    }

                appts = client.get(
                    f"{BASE}/api/v1/tenants/{tenant_id}/appointments",
                    params={
                        "location_id": location_id,
                        "start_from": f"{day}T00:00:00Z",
                        "start_to": f"{day}T23:59:59Z",
                        "limit": 50,
                    },
                    headers=headers,
                )
                evidence["appointments_list"] = appts.status_code == 200
                if appts.status_code == 200:
                    items = appts.json().get("items", appts.json() if isinstance(appts.json(), list) else [])
                    evidence["appointments_listed"] = len(items)

            # Cross-tenant probe with fake tenant id should 403/404
            fake = "00000000-0000-4000-8000-000000000099"
            xt = client.get(
                f"{BASE}/api/v1/tenants/{fake}/patients",
                headers={**headers, "X-Tenant": fake},
            )
            evidence["cross_tenant_patients_blocked"] = xt.status_code in (401, 403, 404)

            logout = client.post(
                f"{BASE}/api/v1/auth/native/logout",
                headers={"Authorization": f"Bearer {token}"},
            )
            evidence["native_logout"] = logout.status_code in (200, 204)

        evidence["pass"] = all(
            [
                evidence.get("healthz"),
                evidence.get("native_login"),
                evidence.get("patients_list"),
                evidence.get("patient_create"),
                evidence.get("patient_overview"),
                evidence.get("patient_timeline"),
                evidence.get("patient_patch"),
                evidence.get("appointment_create"),
                evidence.get("reception_queue"),
                evidence.get("cross_tenant_patients_blocked"),
            ]
        )
    except Exception as e:
        evidence["error"] = type(e).__name__
        evidence["pass"] = False

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    return 0 if evidence.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
