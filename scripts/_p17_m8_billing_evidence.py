"""Phase 1.7 M8 billing evidence — synthetic INR amounts, no PHI/tokens."""

from __future__ import annotations

import json
import os
import uuid
from datetime import date, timedelta
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
    / "phase-1-7"
    / "evidence"
    / "m8_billing_evidence.json"
)


def main() -> int:
    evidence: dict = {
        "phase": "M8",
        "api_base": BASE,
        "synthetic_user": EMAIL,
        "tokens_in_evidence": False,
        "phi_in_evidence": False,
        "amounts_are_backend_strings": True,
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
                    "device_label": "M8-Evidence",
                    "client_instance_id": "m8-evidence",
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

            locs = client.get(
                f"{BASE}/api/v1/tenants/{tenant_id}/locations", headers=headers
            ).json()
            location_id = locs[0]["id"]

            patient = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/patients",
                headers=headers,
                json={"display_name": f"M8 Billing PoC {uuid.uuid4().hex[:6]}"},
            ).json()
            pid = patient["id"]
            evidence["patient_create"] = True

            # Create draft estimate with a line
            est = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/estimates",
                headers=headers,
                json={
                    "patient_id": pid,
                    "location_id": location_id,
                    "valid_until": (date.today() + timedelta(days=14)).isoformat(),
                    "notes": "synthetic estimate",
                    "items": [
                        {
                            "description": "Synthetic consult fee",
                            "quantity": "1",
                            "unit_rate": "500.00",
                            "sequence": 1,
                        }
                    ],
                    "idempotency_key": f"est-{uuid.uuid4().hex[:12]}",
                },
            )
            evidence["estimate_create"] = est.status_code in (200, 201)
            evidence["estimate_create_status"] = est.status_code
            if est.status_code not in (200, 201):
                evidence["estimate_create_detail"] = est.text[:240]
                raise RuntimeError("estimate_create_failed")
            eid = est.json()["id"]
            evidence["estimate_grand_total"] = est.json().get("grand_total")
            evidence["estimate_status_draft"] = est.json().get("status") == "draft"

            issued = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/estimates/{eid}/issue",
                headers=headers,
                json={},
            )
            evidence["estimate_issue"] = issued.status_code == 200
            evidence["estimate_issue_status"] = issued.status_code
            if issued.status_code != 200:
                evidence["estimate_issue_detail"] = issued.text[:240]

            # Duplicate convert protection / convert
            key = f"cvt-{uuid.uuid4().hex[:12]}"
            inv1 = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/estimates/{eid}/convert",
                headers=headers,
                json={"idempotency_key": key},
            )
            evidence["estimate_convert"] = inv1.status_code in (200, 201)
            evidence["estimate_convert_status"] = inv1.status_code
            if inv1.status_code not in (200, 201):
                evidence["estimate_convert_detail"] = inv1.text[:240]
                raise RuntimeError("convert_failed")
            invoice = inv1.json()
            iid = invoice["id"]
            evidence["invoice_from_convert_status"] = invoice.get("status")
            evidence["invoice_grand_total"] = invoice.get("grand_total")
            evidence["invoice_outstanding_after_convert"] = invoice.get(
                "outstanding_amount"
            )

            # Idempotent replay of convert
            inv2 = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/estimates/{eid}/convert",
                headers=headers,
                json={"idempotency_key": key},
            )
            evidence["convert_idempotent_replay"] = inv2.status_code in (200, 201, 409)
            evidence["convert_replay_status"] = inv2.status_code

            # Issue invoice (convert creates draft)
            if invoice.get("status") == "draft":
                iss = client.post(
                    f"{BASE}/api/v1/tenants/{tenant_id}/invoices/{iid}/issue",
                    headers=headers,
                    json={},
                )
                evidence["invoice_issue"] = iss.status_code == 200
                evidence["invoice_issue_status"] = iss.status_code
                if iss.status_code == 200:
                    invoice = iss.json()
                    evidence["invoice_doc_number"] = invoice.get("doc_number")
                    evidence["invoice_financial_year"] = invoice.get("financial_year")
            else:
                evidence["invoice_issue"] = True

            # Partial payment
            pay_key = f"pay-{uuid.uuid4().hex[:12]}"
            pay = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/payments",
                headers={**headers, "Idempotency-Key": pay_key},
                json={
                    "patient_id": pid,
                    "location_id": location_id,
                    "method": "cash",
                    "amount": "200.00",
                    "currency": "INR",
                    "idempotency_key": pay_key,
                },
            )
            evidence["payment_record"] = pay.status_code in (200, 201)
            evidence["payment_status_code"] = pay.status_code
            if pay.status_code not in (200, 201):
                evidence["payment_detail"] = pay.text[:240]
                raise RuntimeError("payment_failed")
            payment = pay.json()
            pay_id = payment["id"]
            evidence["payment_amount"] = payment.get("amount")
            evidence["payment_unallocated"] = payment.get("unallocated_amount")

            # Duplicate payment key replay
            pay_replay = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/payments",
                headers={**headers, "Idempotency-Key": pay_key},
                json={
                    "patient_id": pid,
                    "location_id": location_id,
                    "method": "cash",
                    "amount": "200.00",
                    "currency": "INR",
                    "idempotency_key": pay_key,
                },
            )
            evidence["payment_idempotent_replay"] = pay_replay.status_code in (
                200,
                201,
            )
            evidence["payment_replay_same_id"] = (
                pay_replay.json().get("id") == pay_id
                if pay_replay.status_code in (200, 201)
                else False
            )

            alloc_key = f"alloc-{uuid.uuid4().hex[:12]}"
            alloc = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/payments/{pay_id}/allocations",
                headers=headers,
                json={
                    "allocations": [{"invoice_id": iid, "amount": "200.00"}],
                    "idempotency_key": alloc_key,
                },
            )
            evidence["payment_allocate"] = alloc.status_code in (200, 201)
            evidence["allocate_status"] = alloc.status_code
            if alloc.status_code not in (200, 201):
                evidence["allocate_detail"] = alloc.text[:240]

            # Over-allocation attempt
            over = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/payments/{pay_id}/allocations",
                headers=headers,
                json={
                    "allocations": [{"invoice_id": iid, "amount": "9999.00"}],
                    "idempotency_key": f"over-{uuid.uuid4().hex[:8]}",
                },
            )
            evidence["over_allocation_rejected"] = over.status_code in (400, 409, 422)
            evidence["over_allocation_status"] = over.status_code

            bal = client.get(
                f"{BASE}/api/v1/tenants/{tenant_id}/invoices/{iid}/balance",
                headers=headers,
            )
            evidence["invoice_balance"] = bal.status_code == 200
            if bal.status_code == 200:
                b = bal.json()
                evidence["balance_grand_total"] = b.get("grand_total")
                evidence["balance_allocated"] = b.get("allocated_amount")
                evidence["balance_outstanding"] = b.get("outstanding_amount")
                evidence["partial_payment_reflected"] = (
                    str(b.get("allocated_amount")) == "200.00"
                )

            # Cross-tenant
            fake = "00000000-0000-4000-8000-000000000099"
            xt = client.get(
                f"{BASE}/api/v1/tenants/{fake}/invoices/{iid}",
                headers={**headers, "X-Tenant": fake},
            )
            evidence["cross_tenant_invoice_blocked"] = xt.status_code in (401, 403, 404)

            overview = client.get(
                f"{BASE}/api/v1/tenants/{tenant_id}/patients/{pid}/overview",
                headers=headers,
            )
            evidence["patient_overview"] = overview.status_code == 200
            if overview.status_code == 200:
                evidence["overview_outstanding"] = overview.json().get(
                    "outstanding_balance"
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
                evidence.get("estimate_create"),
                evidence.get("estimate_issue"),
                evidence.get("estimate_convert"),
                evidence.get("invoice_issue"),
                evidence.get("payment_record"),
                evidence.get("payment_allocate"),
                evidence.get("partial_payment_reflected"),
                evidence.get("over_allocation_rejected"),
                evidence.get("cross_tenant_invoice_blocked"),
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
