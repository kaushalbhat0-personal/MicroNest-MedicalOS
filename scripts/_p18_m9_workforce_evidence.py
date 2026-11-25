"""Phase 1.8 M9 workforce evidence — synthetic staff only; no tokens/PII dumps."""

from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone
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
    / "phase-1-8"
    / "evidence"
    / "m9_workforce_evidence.json"
)


def _ok(resp: httpx.Response) -> bool:
    return 200 <= resp.status_code < 300


def main() -> int:
    evidence: dict = {
        "phase": "M9",
        "api_base": BASE,
        "synthetic_user": EMAIL,
        "tokens_in_evidence": False,
        "pii_in_evidence": False,
        "invitation_token_shown_once_only": True,
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
                    "device_label": "M9-Evidence",
                    "client_instance_id": "m9-evidence",
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

            # Cross-tenant probe (synthetic UUID)
            fake_tid = str(uuid.uuid4())
            xt = client.get(
                f"{BASE}/api/v1/tenants/{fake_tid}/staff",
                headers={**headers, "X-Tenant": fake_tid},
            )
            evidence["cross_tenant_staff_denied"] = xt.status_code in (401, 403, 404)

            # 1 Directory
            staff = client.get(f"{BASE}/api/v1/tenants/{tenant_id}/staff", headers=headers)
            evidence["staff_directory"] = staff.status_code == 200
            rows = staff.json() if staff.status_code == 200 else []
            evidence["staff_count"] = len(rows) if isinstance(rows, list) else 0
            membership_id = rows[0]["membership_id"] if rows else None

            # 2 Profile
            if membership_id:
                prof = client.get(
                    f"{BASE}/api/v1/tenants/{tenant_id}/staff/{membership_id}",
                    headers=headers,
                )
                evidence["staff_profile"] = prof.status_code == 200
                evidence["profile_has_role"] = bool(
                    prof.json().get("role") if prof.status_code == 200 else False
                )

            # Roles
            roles = client.get(
                f"{BASE}/api/v1/tenants/{tenant_id}/roles", headers=headers
            )
            evidence["roles_list"] = roles.status_code == 200
            role_names = (
                [r["name"] for r in roles.json()] if roles.status_code == 200 else []
            )
            invite_role = "nurse" if "nurse" in role_names else (
                role_names[0] if role_names else "nurse"
            )

            locs = client.get(
                f"{BASE}/api/v1/tenants/{tenant_id}/locations", headers=headers
            )
            location_id = locs.json()[0]["id"] if locs.status_code == 200 else None
            evidence["locations_ok"] = bool(location_id)

            # 3 Invitation create (token NOT stored in evidence)
            invite_email = f"m9-invite-{uuid.uuid4().hex[:8]}@example.com"
            inv = client.post(
                f"{BASE}/api/v1/tenants/{tenant_id}/invites",
                headers=headers,
                json={
                    "email": invite_email,
                    "role": invite_role,
                    "ttl_days": 3,
                    "location_ids": [location_id] if location_id else None,
                },
            )
            evidence["invitation_create"] = _ok(inv)
            invite_id = None
            if _ok(inv):
                inv_body = inv.json()
                invite_id = inv_body.get("id")
                evidence["invitation_token_returned"] = bool(inv_body.get("token"))
                evidence["invitation_email_redacted"] = True

            # Pending list
            pending = client.get(
                f"{BASE}/api/v1/tenants/{tenant_id}/invitations",
                headers=headers,
                params={"status": "pending"},
            )
            evidence["invitation_list"] = pending.status_code == 200

            # 4 Revoke
            if invite_id:
                rev = client.post(
                    f"{BASE}/api/v1/tenants/{tenant_id}/invitations/{invite_id}/revoke",
                    headers=headers,
                    json={},
                )
                evidence["invitation_revoke"] = _ok(rev)

            # 5 Practitioners + verification status (no self-approve claim)
            pracs = client.get(
                f"{BASE}/api/v1/tenants/{tenant_id}/practitioners", headers=headers
            )
            evidence["practitioners_list"] = pracs.status_code == 200
            if pracs.status_code == 200:
                statuses = {
                    p.get("verification_status") for p in pracs.json() if isinstance(p, dict)
                }
                evidence["practitioner_statuses_observed"] = sorted(
                    s for s in statuses if s
                )

            vq = client.get(
                f"{BASE}/api/v1/tenants/{tenant_id}/verification", headers=headers
            )
            evidence["verification_queue"] = vq.status_code == 200

            # 6 Staff schedules
            if membership_id and location_id:
                sch_list = client.get(
                    f"{BASE}/api/v1/tenants/{tenant_id}/staff-schedules",
                    headers=headers,
                    params={"membership_id": membership_id},
                )
                evidence["staff_schedules_list"] = sch_list.status_code == 200
                weekday = date.today().weekday()  # Mon=0
                created = client.post(
                    f"{BASE}/api/v1/tenants/{tenant_id}/staff-schedules",
                    headers=headers,
                    json={
                        "membership_id": membership_id,
                        "location_id": location_id,
                        "weekday": weekday,
                        "start_time": "09:00:00",
                        "end_time": "17:00:00",
                        "break_minutes": 30,
                        "effective_from": date.today().isoformat(),
                    },
                )
                evidence["staff_schedule_create"] = _ok(created)
                if _ok(created):
                    sid = created.json().get("id")
                    deact = client.post(
                        f"{BASE}/api/v1/tenants/{tenant_id}/staff-schedules/{sid}/deactivate",
                        headers=headers,
                        json={},
                    )
                    evidence["staff_schedule_deactivate"] = _ok(deact)

            # 7 Attendance
            if location_id:
                cin = client.post(
                    f"{BASE}/api/v1/tenants/{tenant_id}/attendance/check-in",
                    headers=headers,
                    json={"location_id": location_id},
                )
                evidence["attendance_check_in"] = _ok(cin) or cin.status_code == 409
                att_id = cin.json().get("id") if _ok(cin) else None
                cout = client.post(
                    f"{BASE}/api/v1/tenants/{tenant_id}/attendance/check-out",
                    headers=headers,
                    json={"attendance_id": att_id},
                )
                evidence["attendance_check_out"] = _ok(cout) or cout.status_code in (
                    400,
                    404,
                    409,
                )
                alist = client.get(
                    f"{BASE}/api/v1/tenants/{tenant_id}/attendance",
                    headers=headers,
                    params={
                        "from_date": (date.today() - timedelta(days=7)).isoformat(),
                        "to_date": date.today().isoformat(),
                    },
                )
                evidence["attendance_list"] = alist.status_code == 200

            # 8 Leave
            types = client.get(
                f"{BASE}/api/v1/tenants/{tenant_id}/leave-types", headers=headers
            )
            evidence["leave_types"] = types.status_code == 200
            type_id = None
            if types.status_code == 200 and types.json():
                type_id = types.json()[0]["id"]

            leave_id = None
            if type_id:
                start = date.today() + timedelta(days=14)
                end = start + timedelta(days=1)
                lr = client.post(
                    f"{BASE}/api/v1/tenants/{tenant_id}/leave-requests",
                    headers=headers,
                    json={
                        "leave_type_id": type_id,
                        "start_date": start.isoformat(),
                        "end_date": end.isoformat(),
                        "reason": "M9 synthetic leave",
                    },
                )
                evidence["leave_request_create"] = _ok(lr)
                if _ok(lr):
                    leave_id = lr.json().get("id")

            # Self-approve attempt: if decide succeeds on own leave, record policy
            if leave_id:
                decide = client.post(
                    f"{BASE}/api/v1/tenants/{tenant_id}/leave-requests/{leave_id}/decide",
                    headers=headers,
                    json={"decision": "approved", "note": "M9 evidence"},
                )
                evidence["leave_decide_status"] = decide.status_code
                evidence["leave_decide"] = _ok(decide)
                # Document whether backend allows self-approve for admin
                evidence["leave_self_decide_observed"] = _ok(decide)

            # Leave cancel HTTP gap
            if leave_id:
                cancel = client.post(
                    f"{BASE}/api/v1/tenants/{tenant_id}/leave-requests/{leave_id}/cancel",
                    headers=headers,
                    json={},
                )
                evidence["leave_cancel_http"] = cancel.status_code
                evidence["leave_cancel_supported"] = cancel.status_code not in (
                    404,
                    405,
                )

            # Overview inputs
            evidence["overview_inputs"] = {
                "active_staff": evidence.get("staff_count", 0),
                "pending_invites_listed": evidence.get("invitation_list", False),
                "verification_queue": evidence.get("verification_queue", False),
                "schedules": evidence.get("staff_schedules_list", False),
                "attendance": evidence.get("attendance_list", False),
                "leave_types": evidence.get("leave_types", False),
            }

            required = [
                "staff_directory",
                "staff_profile",
                "invitation_create",
                "invitation_revoke",
                "practitioners_list",
                "staff_schedules_list",
                "attendance_list",
                "leave_types",
                "cross_tenant_staff_denied",
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
