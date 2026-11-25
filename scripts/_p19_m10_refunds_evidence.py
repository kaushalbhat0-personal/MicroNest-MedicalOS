"""Phase 1.9 M10 refunds/credit-notes evidence — synthetic amounts only."""

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
    / "phase-1-9"
    / "evidence"
    / "m10_refunds_evidence.json"
)


def _ok(resp: httpx.Response) -> bool:
    return 200 <= resp.status_code < 300


def main() -> int:
    evidence: dict = {
        "phase": "M10",
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
                    "device_label": "M10-Evidence",
                    "client_instance_id": "m10-evidence",
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

            # Cross-tenant denial
            fake = str(uuid.uuid4())
            xt = client.get(
                f"{BASE}/api/v1/tenants/{fake}/refunds/{fake}",
                headers={**headers, "X-Tenant": fake},
            )
            evidence["cross_tenant_refund_denied"] = xt.status_code in (401, 403, 404)

            locs = client.get(
                f"{BASE}/api/v1/tenants/{tenant_id}/locations", headers=headers
            ).json()
            location_id = locs[0]["id"]

            patient = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/patients",
                headers=headers,
                json={"display_name": f"M10 Refund PoC {uuid.uuid4().hex[:6]}"},
            ).json()
            pid = patient["id"]
            evidence["patient_create"] = True

            inv = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/invoices",
                headers=headers,
                json={
                    "patient_id": pid,
                    "location_id": location_id,
                    "items": [
                        {
                            "description": "M10 care",
                            "quantity": "1",
                            "unit_rate": "500.00",
                        }
                    ],
                },
            )
            evidence["invoice_create"] = _ok(inv)
            iid = inv.json()["id"]
            issued = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/invoices/{iid}/issue",
                headers=headers,
                json={},
            )
            evidence["invoice_issue"] = _ok(issued)

            pay = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/payments",
                headers=headers,
                json={
                    "patient_id": pid,
                    "location_id": location_id,
                    "method": "cash",
                    "amount": "500.00",
                    "currency": "INR",
                    "idempotency_key": f"m10-pay-{uuid.uuid4().hex[:12]}",
                },
            )
            evidence["payment_record"] = _ok(pay)
            payment_id = pay.json()["id"]

            alloc = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/payments/{payment_id}/allocations",
                headers=headers,
                json={
                    "allocations": [{"invoice_id": iid, "amount": "500.00"}],
                    "idempotency_key": f"m10-alloc-{uuid.uuid4().hex[:12]}",
                },
            )
            evidence["allocation"] = _ok(alloc)

            # Partial refund
            idem = f"m10-ref-{uuid.uuid4().hex[:12]}"
            ref1 = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/payments/{payment_id}/refunds",
                headers=headers,
                json={
                    "amount": "100.00",
                    "reason": "M10 partial refund",
                    "idempotency_key": idem,
                },
            )
            evidence["partial_refund"] = _ok(ref1)
            evidence["partial_refund_amount"] = (
                ref1.json().get("amount") if _ok(ref1) else None
            )

            # Idempotent replay
            ref_replay = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/payments/{payment_id}/refunds",
                headers=headers,
                json={
                    "amount": "100.00",
                    "reason": "M10 partial refund",
                    "idempotency_key": idem,
                },
            )
            evidence["refund_idempotent_replay"] = (
                _ok(ref_replay)
                and ref_replay.json().get("id") == ref1.json().get("id")
            )

            # Over-refund rejection
            over = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/payments/{payment_id}/refunds",
                headers=headers,
                json={
                    "amount": "9999.00",
                    "reason": "M10 over refund attempt",
                    "idempotency_key": f"m10-over-{uuid.uuid4().hex[:12]}",
                },
            )
            evidence["over_refund_rejected"] = over.status_code in (400, 409, 422)

            # List refunds
            listed = client.get(
                f"{BASE}/api/v1/tenants/{tenant_id}/payments/{payment_id}/refunds",
                headers=headers,
            )
            evidence["refund_list"] = listed.status_code == 200

            # Credit note on a fresh invoice with outstanding
            inv2 = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/invoices",
                headers=headers,
                json={
                    "patient_id": pid,
                    "location_id": location_id,
                    "items": [
                        {
                            "description": "M10 CN care",
                            "quantity": "1",
                            "unit_rate": "300.00",
                        }
                    ],
                },
            )
            iid2 = inv2.json()["id"]
            client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/invoices/{iid2}/issue",
                headers=headers,
                json={},
            )

            cn_idem = f"m10-cn-{uuid.uuid4().hex[:12]}"
            draft = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/invoices/{iid2}/credit-notes",
                headers=headers,
                json={
                    "amount": "50.00",
                    "reason": "M10 billing correction",
                    "idempotency_key": cn_idem,
                },
            )
            evidence["credit_note_draft"] = _ok(draft) and draft.json().get("status") == "draft"
            note_id = draft.json()["id"] if _ok(draft) else None

            if note_id:
                issued_cn = client.post(
                    f"{BASE}/api/v1/tenants/{tenant_id}/credit-notes/{note_id}/issue",
                    headers=headers,
                    json={},
                )
                evidence["credit_note_issue"] = (
                    _ok(issued_cn) and issued_cn.json().get("status") == "issued"
                )
                evidence["credit_note_has_doc_number"] = (
                    issued_cn.json().get("doc_number") is not None if _ok(issued_cn) else False
                )

                # Void issued must fail
                void_issued = client.post(
                    f"{BASE}/api/v1/tenants/{tenant_id}/credit-notes/{note_id}/void",
                    headers=headers,
                    json={"reason": "should fail"},
                )
                evidence["void_issued_credit_rejected"] = void_issued.status_code in (
                    400,
                    409,
                    422,
                )

            # Draft void path on another note
            draft2 = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/invoices/{iid2}/credit-notes",
                headers=headers,
                json={
                    "amount": "10.00",
                    "reason": "M10 voidable draft",
                    "idempotency_key": f"m10-cn2-{uuid.uuid4().hex[:12]}",
                },
            )
            if _ok(draft2):
                void_draft = client.post(
                    f"{BASE}/api/v1/tenants/{tenant_id}/credit-notes/{draft2.json()['id']}/void",
                    headers=headers,
                    json={"reason": "M10 void draft"},
                )
                evidence["credit_note_void_draft"] = (
                    _ok(void_draft) and void_draft.json().get("status") == "voided"
                )

            cn_list = client.get(
                f"{BASE}/api/v1/tenants/{tenant_id}/invoices/{iid2}/credit-notes",
                headers=headers,
            )
            evidence["credit_note_list"] = cn_list.status_code == 200

            bal = client.get(
                f"{BASE}/api/v1/tenants/{tenant_id}/invoices/{iid2}/balance",
                headers=headers,
            )
            evidence["invoice_balance_after_cn"] = bal.status_code == 200
            if bal.status_code == 200:
                evidence["outstanding_after_cn"] = bal.json().get("outstanding_amount")

            # Unauthorized: no separate user here — document permission name
            evidence["mutation_permission"] = "billing.refund"
            evidence["read_permission"] = "billing.read"

            # Gaps
            evidence["tenant_wide_refund_list"] = False
            evidence["refund_void_supported"] = False
            evidence["clinic_reconciliation_http"] = False
            evidence["pdf_render"] = False

            required = [
                "partial_refund",
                "refund_idempotent_replay",
                "over_refund_rejected",
                "refund_list",
                "credit_note_draft",
                "credit_note_issue",
                "void_issued_credit_rejected",
                "cross_tenant_refund_denied",
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
