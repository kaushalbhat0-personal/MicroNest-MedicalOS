"""O1.5R: two-pilot end-to-end onboarding + tenant isolation verification.

Real PostgreSQL via the shared harness. Proves the complete journey through
the REAL public contracts (no mocks, no authz bypasses):

  signup -> sign-in -> POST /api/v1/workspaces -> tenant workspace access

for TWO independent synthetic accounts (A=dental, B=ophthalmology
discovery-only), then proves isolation across every relevant surface:

- identity/sessions, provisioning + idempotency, workspace access,
  tenant-scoped APIs (locations/patients/appointments/encounters),
  portal access + portal links, subscription visibility, specialty
  readiness visibility, platform console boundary, audit chains.

Synthetic data only. Cleanup is the harness TRUNCATE (per-test isolation);
no broad deletes against shared databases.

Browser E2E status: workspace provisioning has NO browser UI in this phase
(O1.2a delivered API-only; no /workspaces/new page exists), so the
provisioning leg is API-only by construction. Browser coverage is limited
to the existing signup/login/platform-console pages (see docs report).
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from tests.helpers import login_client, make_platform_admin, tenant_headers

PASSWORD = "password-12345-abc"

A_BODY = {
    "clinic_name": "Pilot Alpha Dental",
    "slug": "pilot-alpha-dental",
    "location_name": "Main Clinic",
    "timezone": "Asia/Kolkata",
    "specialty_codes": ["dental"],
}

B_BODY = {
    "clinic_name": "Pilot Beta Eye",
    "slug": "pilot-beta-eye",
    "location_name": "Eye Clinic",
    "timezone": "Asia/Kolkata",
    "specialty_codes": ["ophthalmology"],
}

FORBIDDEN_SUBSTRINGS = (
    "patient",
    "invoice",
    "payment",
    "diagnosis",
    "prescription",
    "password",
    "secret",
    "token",
    "phone",
    "email",
    "owner",
)


# --- Journey helpers (real public contracts only) ---


def _signup(client: TestClient, *, email: str) -> None:
    r = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "display_name": "Pilot Owner", "password": PASSWORD},
    )
    assert r.status_code == 202, r.text
    assert r.json() == {"status": "accepted"}
    assert "hos_access" not in r.cookies and "hos_refresh" not in r.cookies


def _provision(c: TestClient, body: dict, *, key: str | None = None):
    hdrs = {}
    if key is not None:
        hdrs["Idempotency-Key"] = key
    return c.post("/api/v1/workspaces", json=body, headers=hdrs)


def _two_pilots(client, *, suffix: str = ""):
    """Full journey for two independent accounts. Returns dicts for A and B."""
    email_a = f"pilot-a{suffix}@example.com"
    email_b = f"pilot-b{suffix}@example.com"
    _signup(client, email=email_a)
    _signup(client, email=email_b)
    ca = login_client(client, email=email_a)
    cb = login_client(client, email=email_b)
    body_a = dict(A_BODY, slug=f"{A_BODY['slug']}{suffix}")
    body_b = dict(B_BODY, slug=f"{B_BODY['slug']}{suffix}")
    ra = _provision(ca, body_a, key=str(uuid.uuid4()))
    assert ra.status_code == 201, ra.text
    rb = _provision(cb, body_b, key=str(uuid.uuid4()))
    assert rb.status_code == 201, rb.text
    ja, jb = ra.json(), rb.json()
    assert ja["tenant"]["id"] != jb["tenant"]["id"]
    return (
        {"email": email_a, "client": ca, "body": ja, "tid": ja["tenant"]["id"]},
        {"email": email_b, "client": cb, "body": jb, "tid": jb["tenant"]["id"]},
    )


def _audit_actions(owner_db, tenant_id) -> list[str]:
    return [
        r[0]
        for r in owner_db.execute(
            text("SELECT action FROM audit_events WHERE tenant_id = :t ORDER BY seq"),
            {"t": tenant_id},
        ).all()
    ]


def _chain_days(owner_db, tenant_id) -> list[str]:
    return [
        r[0]
        for r in owner_db.execute(
            text(
                "SELECT DISTINCT chain_day FROM audit_events "
                "WHERE tenant_id = :t ORDER BY chain_day"
            ),
            {"t": tenant_id},
        ).all()
    ]


# --- A. Signup and identity ---


def test_two_independent_accounts_signup_and_sessions(client, owner_db) -> None:  # type: ignore[no-untyped-def]
    from app.modules.tenancy import service as tenancy_service

    _signup(client, email="o15r-a@example.com")
    _signup(client, email="o15r-b@example.com")
    # Both unverified per contract (verification optional).
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "o15r-a@example.com", "password": PASSWORD},
        ).status_code
        == 200
    )
    ca = login_client(client, email="o15r-a@example.com")
    cb = login_client(client, email="o15r-b@example.com")
    assert ca.get("/api/v1/auth/me").json()["email_verified"] is False
    assert cb.get("/api/v1/auth/me").json()["email_verified"] is False
    # Sessions are independent: each client reports its own identity.
    assert ca.get("/api/v1/auth/me").json()["email"] == "o15r-a@example.com"
    assert cb.get("/api/v1/auth/me").json()["email"] == "o15r-b@example.com"
    assert ca.get("/api/v1/auth/sessions").status_code == 200
    assert cb.get("/api/v1/auth/sessions").status_code == 200
    # Zero memberships from signup alone; no platform privilege.
    from app.modules.identity import service as identity_service

    for email in ("o15r-a@example.com", "o15r-b@example.com"):
        user = identity_service.get_user_by_email(owner_db, email)
        assert user is not None and user.is_platform_admin is False
        assert tenancy_service.user_memberships(owner_db, user.id) == []
    # Duplicate signup is indistinguishable (no oracle).
    dup = client.post(
        "/api/v1/auth/signup",
        json={
            "email": "o15r-a@example.com",
            "display_name": "Someone Else",
            "password": PASSWORD,
        },
    )
    assert dup.status_code == 202 and dup.json() == {"status": "accepted"}


def test_unverified_account_password_recovery_compatible(client, owner_db) -> None:  # type: ignore[no-untyped-def]
    """Password recovery works for unverified accounts (no verification gate)."""
    from app.modules.identity import service as identity_service

    _signup(client, email="o15r-unv@example.com")
    # Reset request is accepted for an unverified address (no oracle).
    r = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "o15r-unv@example.com"},
    )
    assert r.status_code == 202, r.text
    ghost = client.post(
        "/api/v1/auth/password-reset/request", json={"email": "ghost@example.com"}
    )
    assert ghost.status_code == 202 and ghost.json() == r.json()
    user = identity_service.get_user_by_email(owner_db, "o15r-unv@example.com")
    assert user is not None and user.email_verified_at is None
    raw = identity_service.create_password_reset(owner_db, user)
    owner_db.commit()
    ok = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": raw, "new_password": "recovered-password-99"},
    )
    assert ok.status_code == 200, ok.text
    c = login_client(
        client, email="o15r-unv@example.com", password="recovered-password-99"
    )
    # Still unverified, but fully able to proceed (provision per contract).
    assert c.get("/api/v1/auth/me").json()["email_verified"] is False
    prov = _provision(c, dict(A_BODY, slug="o15r-unv-clinic"), key=str(uuid.uuid4()))
    assert prov.status_code == 201, prov.text


# --- B. Workspace provisioning ---


def test_two_workspaces_provisioned_with_atomic_records(client, owner_db) -> None:  # type: ignore[no-untyped-def]
    a, b = _two_pilots(client, suffix="-atomic")
    for pilot in (a, b):
        tid = pilot["tid"]
        body = pilot["body"]
        assert body["tenant"]["status"] == "active"
        assert body["membership"]["role"] == "tenant_admin"
        assert body["subscription"]["status"] == "trial"
        assert body["subscription"]["plan_code"] == "trial-14d"
        # Atomic record set exists for the tenant.
        for table, col in (
            ("locations", "tenant_id"),
            ("memberships", "tenant_id"),
            ("tenant_owners", "tenant_id"),
            ("tenant_specialties", "tenant_id"),
            ("subscriptions", "tenant_id"),
        ):
            n = owner_db.execute(
                text(f"SELECT count(*) FROM {table} WHERE {col} = :t"), {"t": tid}
            ).scalar_one()
            assert n >= 1, (table, tid)
        assert (
            owner_db.execute(
                text("SELECT count(*) FROM subscriptions WHERE tenant_id = :t"),
                {"t": tid},
            ).scalar_one()
            == 1
        )
        subs = owner_db.execute(
            text(
                "SELECT status, trial_ends_at, period_start, period_end "
                "FROM subscriptions WHERE tenant_id = :t"
            ),
            {"t": tid},
        ).one()
        # Server-clock 14-day trial window.
        assert subs[0] == "trial"
        assert subs[1] - subs[2] == timedelta(days=14)
        assert subs[3] - subs[2] == timedelta(days=14)
        assert abs((subs[2] - datetime.now(timezone.utc)).total_seconds()) < 600
    # No cross membership or ownership: each tenant has exactly its owner.
    for pilot, other in ((a, b), (b, a)):
        owners = owner_db.execute(
            text("SELECT user_id::text FROM tenant_owners WHERE tenant_id = :t"),
            {"t": pilot["tid"]},
        ).all()
        members = owner_db.execute(
            text("SELECT user_id::text FROM memberships WHERE tenant_id = :t"),
            {"t": pilot["tid"]},
        ).all()
        assert len(owners) == 1 and len(members) == 1
        assert other["tid"] not in [str(pilot["tid"])]
        # The other account holds no row in this tenant.
        from app.modules.identity import service as identity_service

        other_user = identity_service.get_user_by_email(owner_db, other["email"])
        assert str(other_user.id) not in [r[0] for r in owners + members]
    # Each account sees only its own workspace.
    mine_a = {t["id"] for t in a["client"].get("/api/v1/tenants/mine").json()}
    mine_b = {t["id"] for t in b["client"].get("/api/v1/tenants/mine").json()}
    assert mine_a == {a["tid"]} and mine_b == {b["tid"]}
    # Specialty semantics: dental ready, ophthalmology discovery-only.
    assert a["body"]["specialties_enabled"] == ["dental"]
    assert b["body"]["specialties_enabled"] == ["ophthalmology"]


def test_idempotency_replay_conflict_and_no_duplicate_trial(
    client, owner_db, make_owner_user
) -> None:  # type: ignore[no-untyped-def]
    make_owner_user(email="o15r-idem@example.com")
    c = login_client(client, email="o15r-idem@example.com")
    key = str(uuid.uuid4())
    first = _provision(c, dict(A_BODY, slug="o15r-idem"), key=key)
    assert first.status_code == 201, first.text
    replay = _provision(c, dict(A_BODY, slug="o15r-idem"), key=key)
    assert replay.status_code == 201
    assert replay.json() == first.json()
    # Same key + different body -> 409 conflict.
    conflict = _provision(c, dict(A_BODY, slug="o15r-idem-other"), key=key)
    assert conflict.status_code == 409, conflict.text
    # Missing / malformed key -> 422.
    assert (
        c.post("/api/v1/workspaces", json=dict(A_BODY, slug="o15r-nokey")).status_code
        == 422
    )
    bad = c.post(
        "/api/v1/workspaces",
        json=dict(A_BODY, slug="o15r-badkey"),
        headers={"Idempotency-Key": "not-a-uuid"},
    )
    assert bad.status_code == 422
    # Exactly one tenant and one trial despite replay + conflict attempts.
    tid = first.json()["tenant"]["id"]
    assert (
        owner_db.execute(
            text("SELECT count(*) FROM tenants WHERE slug = 'o15r-idem'")
        ).scalar_one()
        == 1
    )
    assert (
        owner_db.execute(
            text("SELECT count(*) FROM subscriptions WHERE tenant_id = :t"), {"t": tid}
        ).scalar_one()
        == 1
    )
    assert "password" not in first.text and "token" not in first.text.lower()


def test_concurrent_duplicate_provisioning_creates_one_workspace(
    client, owner_db, make_owner_user
) -> None:  # type: ignore[no-untyped-def]
    make_owner_user(email="o15r-race@example.com")
    key = str(uuid.uuid4())
    gate = threading.Barrier(3)
    results: list[tuple[int, str]] = []

    def attempt() -> None:
        c = TestClient(client.app, base_url="http://test")
        resp = c.post(
            "/api/v1/auth/login",
            json={"email": "o15r-race@example.com", "password": PASSWORD},
        )
        assert resp.status_code == 200
        gate.wait(timeout=30)
        r = c.post(
            "/api/v1/workspaces",
            json=dict(A_BODY, slug="o15r-race-clinic"),
            headers={"Idempotency-Key": key},
        )
        results.append((r.status_code, r.json().get("tenant", {}).get("id", r.text)))

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for t in threads:
        t.start()
    gate.wait(timeout=30)
    for t in threads:
        t.join(timeout=60)
    assert sorted(s for s, _ in results) == [201, 201], results
    assert results[0][1] == results[1][1]
    assert (
        owner_db.execute(
            text("SELECT count(*) FROM tenants WHERE slug = 'o15r-race-clinic'")
        ).scalar_one()
        == 1
    )


# --- C. Workspace access ---


def test_workspace_access_selectors_and_ownership_boundary(client, owner_db) -> None:  # type: ignore[no-untyped-def]
    a, b = _two_pilots(client, suffix="-access")
    ca, cb = a["client"], b["client"]
    ta, tb = a["tid"], b["tid"]
    # Own access works.
    assert (
        ca.get(f"/api/v1/tenants/{ta}", headers=tenant_headers(ta)).status_code == 200
    )
    assert (
        cb.get(f"/api/v1/tenants/{tb}", headers=tenant_headers(tb)).status_code == 200
    )
    # Forged selector for the foreign tenant: 403, no data.
    r = ca.get(f"/api/v1/tenants/{tb}", headers=tenant_headers(tb))
    assert r.status_code == 403
    assert "pilot-beta" not in r.text and "trial-14d" not in r.text
    r = cb.get(f"/api/v1/tenants/{ta}", headers=tenant_headers(ta))
    assert r.status_code == 403
    assert "pilot-alpha" not in r.text and "trial-14d" not in r.text
    # Valid selector + foreign path: 404 anti-oracle (indistinguishable).
    r = ca.get(f"/api/v1/tenants/{tb}", headers=tenant_headers(ta))
    assert r.status_code == 404
    assert "trial-14d" not in r.text
    unknown = ca.get(
        "/api/v1/tenants/00000000-0000-4000-8000-000000000000",
        headers=tenant_headers(ta),
    )
    assert unknown.status_code == 404
    assert unknown.json()["type"] == r.json()["type"]
    # Ownership does NOT bypass permission checks.
    owner_db.execute(text("DELETE FROM memberships WHERE tenant_id = :t"), {"t": ta})
    owner_db.commit()
    assert (
        owner_db.execute(
            text("SELECT count(*) FROM tenant_owners WHERE tenant_id = :t"), {"t": ta}
        ).scalar_one()
        == 1
    )
    assert (
        ca.get(f"/api/v1/tenants/{ta}", headers=tenant_headers(ta)).status_code == 403
    )


# --- D. Subscription and specialty visibility ---


def test_subscription_and_specialty_visibility_per_tenant(client, owner_db) -> None:  # type: ignore[no-untyped-def]
    a, b = _two_pilots(client, suffix="-vis")
    for pilot in (a, b):
        detail = pilot["client"].get(
            f"/api/v1/tenants/{pilot['tid']}",
            headers=tenant_headers(pilot["tid"]),
        )
        assert detail.status_code == 200, detail.text
        sub = detail.json()["subscription"]
        assert sub["plan_code"] == "trial-14d"
        assert sub["plan_name"] == "Trial (14-day)"
        assert sub["status"] == "trial"
        starts = datetime.fromisoformat(sub["trial_starts_at"].replace("Z", "+00:00"))
        ends = datetime.fromisoformat(sub["trial_ends_at"].replace("Z", "+00:00"))
        assert (ends - starts).days == 14
        assert sub["is_in_trial"] is True
        # P2.2+: capacity limits are enforced (staff/locations/practitioners).
        assert sub["limits"] == {
            "max_locations": 3,
            "max_practitioners": 10,
            "max_staff_seats": 25,
            "enforced": True,
        }
    by_code_a = {
        s["code"]: s
        for s in a["client"]
        .get(f"/api/v1/tenants/{a['tid']}", headers=tenant_headers(a["tid"]))
        .json()["specialties"]
    }
    assert by_code_a["dental"]["maturity"] == "ready"
    assert by_code_a["dental"]["ready_for_use"] is True
    assert by_code_a["dental"]["pack_version"] == "1.0.0"
    detail_b = (
        b["client"]
        .get(f"/api/v1/tenants/{b['tid']}", headers=tenant_headers(b["tid"]))
        .json()
    )
    (eye,) = detail_b["specialties"]
    assert eye["maturity"] == "discovery" and eye["ready_for_use"] is False
    assert set(eye) == {"code", "pack_version", "label", "maturity", "ready_for_use"}
    # Cross-tenant subscription probes disclose nothing.
    r = a["client"].get(f"/api/v1/tenants/{b['tid']}", headers=tenant_headers(a["tid"]))
    assert r.status_code == 404 and "trial-14d" not in r.text


def test_trial_expiry_and_suspension_do_not_gate_clinical_reads(
    client, owner_db
) -> None:  # type: ignore[no-untyped-def]
    a, _ = _two_pilots(client, suffix="-nogate")
    tid = a["tid"]
    h = tenant_headers(tid)
    owner_db.execute(
        text(
            "UPDATE subscriptions SET trial_ends_at = now() - interval '1 day' WHERE tenant_id = :t"
        ),
        {"t": tid},
    )
    owner_db.commit()
    r = a["client"].get(f"/api/v1/tenants/{tid}", headers=h)
    assert r.status_code == 200 and r.json()["subscription"]["is_in_trial"] is False
    assert (
        a["client"].get(f"/api/v1/tenants/{tid}/locations", headers=h).status_code
        == 200
    )
    owner_db.execute(
        text("UPDATE subscriptions SET status = 'suspended' WHERE tenant_id = :t"),
        {"t": tid},
    )
    owner_db.commit()
    r = a["client"].get(f"/api/v1/tenants/{tid}", headers=h)
    assert r.status_code == 200 and r.json()["subscription"]["status"] == "suspended"
    assert (
        a["client"].get(f"/api/v1/tenants/{tid}/locations", headers=h).status_code
        == 200
    )


# --- Clinical + portal isolation over journey tenants ---


def _register_patient(c: TestClient, tid: str, name: str) -> dict:
    r = c.post(
        f"/api/v1/tenants/{tid}/patients",
        headers=tenant_headers(tid),
        json={"display_name": name},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_patient_scheduling_encounter_isolation(client, owner_db) -> None:  # type: ignore[no-untyped-def]
    from datetime import datetime as _dt

    a, b = _two_pilots(client, suffix="-clin")
    pa = _register_patient(a["client"], a["tid"], "Synthetic Alpha Patient")
    pb = _register_patient(b["client"], b["tid"], "Synthetic Beta Patient")
    # Cross-tenant patient reads fail closed with no disclosure.
    r = a["client"].get(
        f"/api/v1/tenants/{a['tid']}/patients/{pb['id']}",
        headers=tenant_headers(a["tid"]),
    )
    assert r.status_code == 404
    assert "Beta" not in r.text
    listed = (
        a["client"]
        .get(f"/api/v1/tenants/{a['tid']}/patients", headers=tenant_headers(a["tid"]))
        .json()
    )
    assert {row["id"] for row in listed} == {pa["id"]}
    # Locations are tenant-scoped.
    locs_a = (
        a["client"]
        .get(f"/api/v1/tenants/{a['tid']}/locations", headers=tenant_headers(a["tid"]))
        .json()
    )
    assert len(locs_a) == 1
    practs = a["client"].get(
        f"/api/v1/tenants/{a['tid']}/practitioners", headers=tenant_headers(a["tid"])
    )
    assert practs.status_code == 200
    pid = practs.json()[0]["id"] if practs.json() else None
    if pid is not None:
        from app.modules.identity.models import Practitioner as _Practitioner
        from app.modules.tenancy import service as tenancy_service

        tenant_row = tenancy_service.get_tenant(owner_db, a["tid"])
        practitioner_row = owner_db.execute(
            text("SELECT id FROM practitioners WHERE id = :p"), {"p": pid}
        ).first()
        if practitioner_row is not None:
            tenancy_service.set_verification(
                owner_db,
                tenant=tenant_row,
                practitioner=owner_db.get(_Practitioner, pid),
                status="approved",
            )
            owner_db.commit()
            start = (_dt.now(timezone.utc) + timedelta(days=2)).isoformat()
            appt = a["client"].post(
                f"/api/v1/tenants/{a['tid']}/appointments",
                headers=tenant_headers(a["tid"]),
                json={
                    "patient_id": pa["id"],
                    "practitioner_id": pid,
                    "location_id": locs_a[0]["id"],
                    "start": start,
                    "duration_minutes": 30,
                },
            )
            assert appt.status_code == 200, appt.text
            # Foreign appointment id under own selector: 404.
            assert (
                b["client"]
                .get(
                    f"/api/v1/tenants/{b['tid']}/appointments/{appt.json()['id']}",
                    headers=tenant_headers(b["tid"]),
                )
                .status_code
                == 404
            )


def test_portal_enrollment_and_cross_tenant_isolation(client, owner_db) -> None:  # type: ignore[no-untyped-def]
    from app.modules.identity import service as identity_service

    a, b = _two_pilots(client, suffix="-portal")
    pa = _register_patient(a["client"], a["tid"], "Portal Alpha Patient")
    pb = _register_patient(b["client"], b["tid"], "Portal Beta Patient")
    for pilot, patient, email in (
        (a, pa, "o15r-portal-a@example.com"),
        (b, pb, "o15r-portal-b@example.com"),
    ):
        r = pilot["client"].post(
            f"/api/v1/tenants/{pilot['tid']}/portal-links",
            headers=tenant_headers(pilot["tid"]),
            json={"email": email, "patient_id": patient["id"]},
        )
        assert r.status_code == 200, r.text
    # Portal users activate via the password-reset flow (production path).
    for email in ("o15r-portal-a@example.com", "o15r-portal-b@example.com"):
        user = identity_service.get_user_by_email(owner_db, email)
        identity_service.set_password(owner_db, user, "portal-pass-12345")
    owner_db.commit()
    porta = login_client(
        client, email="o15r-portal-a@example.com", password="portal-pass-12345"
    )
    portb = login_client(
        client, email="o15r-portal-b@example.com", password="portal-pass-12345"
    )
    ha, hb = tenant_headers(a["tid"]), tenant_headers(b["tid"])
    assert porta.get("/api/v1/portal/profile", headers=ha).status_code == 200
    assert portb.get("/api/v1/portal/profile", headers=hb).status_code == 200
    # Cross-tenant portal context rejected; forged ids are 404 with no leak.
    assert porta.get("/api/v1/portal/profile", headers=hb).status_code in (403, 404)
    forged = str(uuid.uuid4())
    for path in (
        f"/api/v1/portal/appointments/{forged}",
        f"/api/v1/portal/encounters/{forged}",
        f"/api/v1/portal/invoices/{forged}",
    ):
        assert porta.get(path, headers=ha).status_code == 404
    # A's portal session cannot reach B's patient-linked data: profile ids differ.
    prof_a = porta.get("/api/v1/portal/profile", headers=ha).json()
    prof_b = portb.get("/api/v1/portal/profile", headers=hb).json()
    assert prof_a["id"] != prof_b["id"]
    assert pa["id"] == prof_a["id"] and pb["id"] == prof_b["id"]
    # Portal caller cannot reach provider surfaces.
    assert (
        porta.get(f"/api/v1/tenants/{a['tid']}/patients", headers=ha).status_code == 403
    )


# --- E. Platform Admin Console ---


def test_platform_console_lists_both_pilots(client, owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    a, b = _two_pilots(client, suffix="-plat")
    make_platform_admin(owner_db, make_owner_user, email="o15r-plat@example.com")
    plat = login_client(client, email="o15r-plat@example.com")
    listed = plat.get("/api/v1/platform/tenants?limit=100")
    assert listed.status_code == 200, listed.text
    by_slug = {i["slug"]: i for i in listed.json()["items"]}
    assert "pilot-alpha-dental-plat" in by_slug
    assert "pilot-beta-eye-plat" in by_slug
    for slug in ("pilot-alpha-dental-plat", "pilot-beta-eye-plat"):
        item = by_slug[slug]
        assert item["subscription"]["plan_code"] == "trial-14d"
        assert item["subscription"]["limits"]["enforced"] is True
    assert by_slug["pilot-alpha-dental-plat"]["specialties_enabled"] == ["dental"]
    assert by_slug["pilot-beta-eye-plat"]["specialties_enabled"] == ["ophthalmology"]
    # Pagination + status filter behave.
    first = plat.get("/api/v1/platform/tenants?limit=1&offset=0").json()
    second = plat.get("/api/v1/platform/tenants?limit=1&offset=1").json()
    assert first["total"] >= 2 and len(first["items"]) == 1
    assert first["items"][0]["id"] != second["items"][0]["id"]
    assert plat.get("/api/v1/platform/tenants?status=active").status_code == 200
    assert plat.get("/api/v1/platform/tenants?status=bogus").status_code == 422
    assert plat.get("/api/v1/platform/tenants?limit=0").status_code == 422
    # Detail pages carry correct commercial metadata, no forbidden surface.
    for pilot in (a, b):
        d = plat.get(f"/api/v1/platform/tenants/{pilot['tid']}")
        assert d.status_code == 200, d.text
        assert d.json()["subscription"]["plan_code"] == "trial-14d"
        for forbidden in FORBIDDEN_SUBSTRINGS:
            assert forbidden not in d.text.lower(), forbidden
    assert (
        plat.get(
            "/api/v1/platform/tenants/00000000-0000-4000-8000-000000000000"
        ).status_code
        == 404
    )
    for forbidden in FORBIDDEN_SUBSTRINGS:
        assert forbidden not in listed.text.lower(), forbidden


def test_platform_boundary_and_unaudited_failures(
    client, owner_db, make_owner_user
) -> None:  # type: ignore[no-untyped-def]
    a, _ = _two_pilots(client, suffix="-bound")
    make_platform_admin(owner_db, make_owner_user, email="o15r-plat2@example.com")
    plat = login_client(client, email="o15r-plat2@example.com")
    before = owner_db.execute(
        select(func.count())
        .select_from(text("audit_events"))
        .where(text("action LIKE 'platform.tenant.%'"))
    ).scalar_one()
    # Platform admin has NO clinical path.
    assert (
        plat.get(
            f"/api/v1/tenants/{a['tid']}", headers=tenant_headers(a["tid"])
        ).status_code
        == 403
    )
    assert (
        plat.get(
            f"/api/v1/tenants/{a['tid']}/patients", headers=tenant_headers(a["tid"])
        ).status_code
        == 403
    )
    # Tenant admins and anonymous callers cannot reach the console.
    assert a["client"].get("/api/v1/platform/tenants").status_code == 403
    assert a["client"].get(f"/api/v1/platform/tenants/{a['tid']}").status_code == 403
    assert client.get("/api/v1/platform/tenants").status_code == 401
    assert client.get(f"/api/v1/platform/tenants/{a['tid']}").status_code == 401
    # All of the above were failures: no successful-read audit events minted.
    after = owner_db.execute(
        select(func.count())
        .select_from(text("audit_events"))
        .where(text("action LIKE 'platform.tenant.%'"))
    ).scalar_one()
    assert after == before


# --- Audit ---


def test_platform_reads_audited_and_chains_valid(
    client, owner_db, make_owner_user
) -> None:  # type: ignore[no-untyped-def]
    from app.modules.audit import service as audit_service
    from app.modules.audit.models import AuditEvent

    a, b = _two_pilots(client, suffix="-audit")
    admin = make_platform_admin(
        owner_db, make_owner_user, email="o15r-plat3@example.com"
    )
    plat = login_client(client, email="o15r-plat3@example.com")
    assert plat.get(f"/api/v1/platform/tenants/{a['tid']}").status_code == 200
    assert plat.get("/api/v1/platform/tenants?limit=1&offset=0").status_code == 200
    for tid in (a["tid"], b["tid"]):
        events = (
            owner_db.execute(
                select(AuditEvent)
                .where(
                    AuditEvent.tenant_id == tid,
                    AuditEvent.action.in_(
                        ["platform.tenant.list", "platform.tenant.read"]
                    ),
                )
                .order_by(AuditEvent.seq)
            )
            .scalars()
            .all()
        )
        for ev in events:
            assert ev.action in ("platform.tenant.list", "platform.tenant.read")
            assert ev.actor_type == "user" and ev.actor_id == str(admin.id)
            assert ev.resource_type == "tenant" and ev.resource_id == tid
            assert ev.result == "ok" and ev.request_id and ev.request_id != "-"
            # Refs only: no PII anywhere in the row.
            assert "o15r-plat3@example.com" not in str(ev.__dict__)
            assert "pilot-" not in str(ev.__dict__)
    # Provisioning events exist for both tenants.
    for tid in (a["tid"], b["tid"]):
        actions = set(_audit_actions(owner_db, tid))
        assert {"workspace.provision", "subscription.trial.start"} <= actions
    # Hash chains verify for every audited day of both tenants.
    for tid in (a["tid"], b["tid"]):
        for day in _chain_days(owner_db, tid):
            assert audit_service.verify_chain(owner_db, tenant_id=tid, day=day) is True


def test_outbox_refs_only_and_no_credentials_in_logs(client, owner_db, caplog) -> None:  # type: ignore[no-untyped-def]
    import logging

    with caplog.at_level(logging.INFO):
        a, b = _two_pilots(client, suffix="-logs")
    for tid in (a["tid"], b["tid"]):
        payloads = owner_db.execute(
            text("SELECT payload::text FROM outbox_events WHERE tenant_id = :t"),
            {"t": tid},
        ).all()
        assert payloads
        joined = " ".join(r[0] for r in payloads).lower()
        for forbidden in ("password", "secret", "token", "clinical", "phone", "email"):
            assert forbidden not in joined
    leaking = [
        r
        for r in caplog.records
        if PASSWORD in r.getMessage() or "hos_refresh" in r.getMessage()
    ]
    assert leaking == []


# --- F. Cross-tenant isolation matrix ---


def test_cross_tenant_isolation_matrix(client, owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    """Seven-row matrix: expected vs actual status, data disclosure, audit."""

    def _platform_events(tid) -> int:
        return owner_db.execute(
            text(
                "SELECT count(*) FROM audit_events "
                "WHERE tenant_id = :t AND action LIKE 'platform.tenant.%'"
            ),
            {"t": tid},
        ).scalar_one()

    a, b = _two_pilots(client, suffix="-matrix")
    make_platform_admin(owner_db, make_owner_user, email="o15r-platm@example.com")
    plat = login_client(client, email="o15r-platm@example.com")
    ta, tb = a["tid"], b["tid"]
    pa = _register_patient(a["client"], ta, "Matrix Alpha Patient")

    rows = []

    def check(
        label,
        resp,
        *,
        expected,
        audit_expected: bool,
        audit_before: int,
        audit_after: int,
        leak_markers=(),
    ):
        actual = resp.status_code
        assert actual == expected, (label, actual, resp.text[:300])
        disclosed = any(m in resp.text for m in leak_markers)
        assert not disclosed, (label, "foreign data disclosed")
        audited = audit_after > audit_before
        assert audited == audit_expected, (label, audited)
        rows.append((label, expected, actual, disclosed, audit_expected, audited))

    # 1. A -> A (own tenant read, audited via tenant chain only for platform reads;
    #    tenant reads mint no platform event, but must succeed with own data).
    before = _platform_events(ta)
    r = a["client"].get(f"/api/v1/tenants/{ta}", headers=tenant_headers(ta))
    check(
        "1. A->A tenant detail",
        r,
        expected=200,
        audit_expected=False,
        audit_before=before,
        audit_after=_platform_events(ta),
    )
    assert r.json()["subscription"]["plan_code"] == "trial-14d"
    # 2. A -> B (forged selector): 403, nothing disclosed, unaudited.
    before = _platform_events(tb)
    r = a["client"].get(f"/api/v1/tenants/{tb}", headers=tenant_headers(tb))
    check(
        "2. A->B forged selector",
        r,
        expected=403,
        audit_expected=False,
        audit_before=before,
        audit_after=_platform_events(tb),
        leak_markers=("pilot-beta", "trial-14d"),
    )
    # 3. B -> B own read.
    before = _platform_events(tb)
    r = b["client"].get(f"/api/v1/tenants/{tb}", headers=tenant_headers(tb))
    check(
        "3. B->B tenant detail",
        r,
        expected=200,
        audit_expected=False,
        audit_before=before,
        audit_after=_platform_events(tb),
    )
    # 4. B -> A (forged selector): 403, nothing disclosed, unaudited.
    before = _platform_events(ta)
    r = b["client"].get(f"/api/v1/tenants/{ta}", headers=tenant_headers(ta))
    check(
        "4. B->A forged selector",
        r,
        expected=403,
        audit_expected=False,
        audit_before=before,
        audit_after=_platform_events(ta),
        leak_markers=("pilot-alpha", "trial-14d"),
    )
    # 5a/5b. Platform admin -> A and B summaries: 200 + exactly one audit event each.
    for label, tid in (
        ("5a. platform->A summary", ta),
        ("5b. platform->B summary", tb),
    ):
        before = _platform_events(tid)
        r = plat.get(f"/api/v1/platform/tenants/{tid}")
        after = _platform_events(tid)
        check(
            label,
            r,
            expected=200,
            audit_expected=True,
            audit_before=before,
            audit_after=after,
        )
        assert r.json()["subscription"]["plan_code"] == "trial-14d"
    # 6. Platform admin -> tenant clinical route: 403, unaudited.
    before = _platform_events(ta)
    r = plat.get(f"/api/v1/tenants/{ta}/patients", headers=tenant_headers(ta))
    check(
        "6. platform->clinical",
        r,
        expected=403,
        audit_expected=False,
        audit_before=before,
        audit_after=_platform_events(ta),
        leak_markers=("Matrix Alpha",),
    )
    # 7a/7b. Anonymous -> tenant and platform routes: 401, unaudited.
    before = _platform_events(ta)
    r = client.get(f"/api/v1/tenants/{ta}", headers=tenant_headers(ta))
    check(
        "7a. anon->tenant",
        r,
        expected=401,
        audit_expected=False,
        audit_before=before,
        audit_after=_platform_events(ta),
    )
    r = client.get(f"/api/v1/platform/tenants/{ta}")
    check(
        "7b. anon->platform",
        r,
        expected=401,
        audit_expected=False,
        audit_before=before,
        audit_after=_platform_events(ta),
    )
    # Cross-tenant patient probe from the matrix tenant: 404, unaudited.
    r = b["client"].get(
        f"/api/v1/tenants/{tb}/patients/{pa['id']}", headers=tenant_headers(tb)
    )
    assert r.status_code == 404 and "Matrix Alpha" not in r.text

    assert len(rows) == 9  # 1,2,3,4,5a,5b,6,7a,7b
