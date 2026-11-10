"""O1.2a: atomic workspace provisioning (`POST /api/v1/workspaces`).

Real PostgreSQL via the shared harness. Covers: API + validation,
atomicity (fault injection at every stage), idempotency, authorization +
isolation, trial semantics, and the additive tenant-detail extension.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from tests.helpers import login_client, tenant_headers

BASE_BODY = {
    "clinic_name": "Nevase Dental",
    "slug": "nevase-dental",
    "location_name": "Main Clinic",
    "timezone": "Asia/Kolkata",
    "specialty_codes": ["dental"],
}


def _provision(
    c: TestClient,
    body: dict | None = None,
    *,
    key: str | None = None,
    headers: dict | None = None,
):  # type: ignore[no-untyped-def]
    payload = dict(BASE_BODY)
    if body:
        payload.update(body)
    hdrs = dict(headers or {})
    if key is not None:
        hdrs["Idempotency-Key"] = key
    return c.post("/api/v1/workspaces", json=payload, headers=hdrs)


def _counts(owner_db) -> dict:  # type: ignore[no-untyped-def]
    tables = [
        "tenants",
        "locations",
        "memberships",
        "tenant_owners",
        "practitioners",
        "practitioner_verifications",
        "tenant_specialties",
        "subscriptions",
        "audit_events",
        "outbox_events",
        "workspace_provisions",
    ]
    return {
        t: owner_db.execute(select(func.count()).select_from(text(t))).scalar_one()
        for t in tables
    }


def _signup_and_login(client, email: str) -> TestClient:  # type: ignore[no-untyped-def]
    r = client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "display_name": "Doc Owner",
            "password": "password-12345-abc",
        },
    )
    assert r.status_code == 202, r.text
    return login_client(client, email=email)


# --- API + validation ---


def test_provisioning_succeeds(client, owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    user = make_owner_user(email="owner-a@example.com")
    c = login_client(client, email="owner-a@example.com")
    r = _provision(c, key=str(uuid.uuid4()))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["tenant"]["slug"] == "nevase-dental"
    assert body["tenant"]["status"] == "active"
    assert body["location"]["timezone"] == "Asia/Kolkata"
    assert body["membership"]["role"] == "tenant_admin"
    assert body["practitioner"]["display_name"]
    assert body["specialties_enabled"] == ["dental"]
    assert body["subscription"]["status"] == "trial"
    assert body["subscription"]["plan_code"] == "trial-14d"
    assert "password" not in r.text and "token" not in r.text
    # Owner row mirrors the caller.
    assert str(user.id) in {
        row[0]
        for row in owner_db.execute(
            text("SELECT user_id::text FROM tenant_owners WHERE tenant_id = :t"),
            {"t": body["tenant"]["id"]},
        ).all()
    }


def test_unauthenticated_provisioning_fails(client) -> None:  # type: ignore[no-untyped-def]
    r = _provision(client, key=str(uuid.uuid4()))
    assert r.status_code == 401


def test_unverified_user_can_provision(client) -> None:  # type: ignore[no-untyped-def]
    c = _signup_and_login(client, "fresh-doc@example.com")
    me = c.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email_verified"] is False  # still unverified
    r = _provision(c, {"slug": "unverified-clinic"}, key=str(uuid.uuid4()))
    assert r.status_code == 201, r.text


def test_invalid_timezone_rejected(client, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    make_owner_user(email="owner-b@example.com")
    c = login_client(client, email="owner-b@example.com")
    r = _provision(
        c, {"slug": "bad-tz", "timezone": "Mars/Olympus"}, key=str(uuid.uuid4())
    )
    assert r.status_code == 422, r.text


def test_unsupported_specialty_rejected(client, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    make_owner_user(email="owner-c@example.com")
    c = login_client(client, email="owner-c@example.com")
    r = _provision(
        c,
        {"slug": "bad-spec", "specialty_codes": ["cardiology"]},
        key=str(uuid.uuid4()),
    )
    assert r.status_code == 422, r.text
    r = _provision(
        c, {"slug": "empty-spec", "specialty_codes": []}, key=str(uuid.uuid4())
    )
    assert r.status_code == 422, r.text


def test_missing_fields_rejected(client, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    make_owner_user(email="owner-d@example.com")
    c = login_client(client, email="owner-d@example.com")
    r = c.post(
        "/api/v1/workspaces",
        json={"slug": "no-name"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 422, r.text


def test_caller_supplied_owner_ids_ignored(client, owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    caller = make_owner_user(email="caller@example.com")
    other = make_owner_user(email="victim@example.com")
    c = login_client(client, email="caller@example.com")
    r = _provision(
        c,
        {
            "slug": "hijack-clinic",
            "owner_user_id": str(other.id),
            "user_id": str(other.id),
            "owner": str(other.id),
        },
        key=str(uuid.uuid4()),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    owners = owner_db.execute(
        text("SELECT user_id::text FROM tenant_owners WHERE tenant_id = :t"),
        {"t": body["tenant"]["id"]},
    ).all()
    assert [row[0] for row in owners] == [str(caller.id)]
    members = owner_db.execute(
        text("SELECT user_id::text FROM memberships WHERE tenant_id = :t"),
        {"t": body["tenant"]["id"]},
    ).all()
    assert [row[0] for row in members] == [str(caller.id)]


def test_x_tenant_not_required_and_ignored(client, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    make_owner_user(email="owner-e@example.com")
    c = login_client(client, email="owner-e@example.com")
    # No X-Tenant: succeeds.
    r = _provision(c, {"slug": "no-xtenant"}, key=str(uuid.uuid4()))
    assert r.status_code == 201, r.text
    # Bogus X-Tenant: ignored, still succeeds (workspace creation needs none).
    r = _provision(
        c,
        {"slug": "bogus-xtenant"},
        key=str(uuid.uuid4()),
        headers={"X-Tenant": str(uuid.uuid4())},
    )
    assert r.status_code == 201, r.text


def test_idempotency_key_required(client, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    make_owner_user(email="owner-f@example.com")
    c = login_client(client, email="owner-f@example.com")
    assert _provision(c, {"slug": "no-key"}).status_code == 422
    r = c.post(
        "/api/v1/workspaces",
        json=dict(BASE_BODY, slug="bad-key"),
        headers={"Idempotency-Key": "not-a-uuid"},
    )
    assert r.status_code == 422, r.text


def test_slug_taken_is_409(client, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    make_owner_user(email="owner-g@example.com")
    c = login_client(client, email="owner-g@example.com")
    assert (
        _provision(c, {"slug": "taken-slug"}, key=str(uuid.uuid4())).status_code == 201
    )
    r = _provision(c, {"slug": "taken-slug"}, key=str(uuid.uuid4()))
    assert r.status_code == 409, r.text


def test_reserved_slug_rejected(client, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    make_owner_user(email="owner-h@example.com")
    c = login_client(client, email="owner-h@example.com")
    r = _provision(c, {"slug": "admin"}, key=str(uuid.uuid4()))
    assert r.status_code == 422, r.text


def test_defaults_applied(client, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    user = make_owner_user(email="owner-i@example.com")
    c = login_client(client, email="owner-i@example.com")
    r = _provision(
        c,
        {
            "clinic_name": "Defaulted",
            "slug": "defaulted",
            "specialty_codes": ["dental"],
        },
        key=str(uuid.uuid4()),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["location"]["name"] == "Main Clinic"
    assert body["location"]["timezone"] == "Asia/Kolkata"
    assert body["practitioner"]["display_name"] == user.display_name


# --- Atomicity (fault injection at every stage) ---


def _boom(*args, **kwargs):  # type: ignore[no-untyped-def]
    raise RuntimeError("injected failure")


@pytest.mark.parametrize(
    "target,tag",
    [
        ("app.modules.clinics.service.create_location", "location"),
        ("app.modules.tenancy.service.create_membership", "membership"),
        ("app.modules.tenancy.service.create_owner", "owner"),
        ("app.modules.tenancy.service.register_practitioner", "practitioner"),
        ("app.modules.workspaces.registry.validate_specialty_codes", "specialties"),
        ("app.modules.subscriptions.service.create_trial_subscription", "trial"),
        ("app.modules.audit.service.append", "audit"),
        ("app.platform.events.service.emit", "outbox"),
    ],
)
def test_fault_at_any_stage_leaves_zero_rows(  # type: ignore[no-untyped-def]
    client, owner_db, make_owner_user, monkeypatch, target, tag
) -> None:
    email = f"fault-{tag}@example.com"
    make_owner_user(email=email)
    # Unhandled faults must surface as 500 responses, not test-client raises.
    raw = TestClient(client.app, base_url="http://test", raise_server_exceptions=False)
    login = raw.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password-12345-abc"},
    )
    assert login.status_code == 200, login.text
    before = _counts(owner_db)
    monkeypatch.setattr(target, _boom)
    r = raw.post(
        "/api/v1/workspaces",
        json=dict(BASE_BODY, slug=f"fault-{tag}"),
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 500, r.text
    assert _counts(owner_db) == before


def test_slug_conflict_mid_path_rolls_back(client, owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    make_owner_user(email="race-owner@example.com")
    c = login_client(client, email="race-owner@example.com")
    before = _counts(owner_db)
    # Pre-create the slug via the operator path so provisioning fails AFTER
    # validating everything else (tenant insert is the first write).
    from app.modules.tenancy import service as tenancy_service

    tenancy_service.create_tenant(owner_db, name="Taken", slug="operator-taken")
    owner_db.commit()
    r = _provision(c, {"slug": "operator-taken"}, key=str(uuid.uuid4()))
    assert r.status_code == 409, r.text
    after = _counts(owner_db)
    assert after["tenants"] == before["tenants"] + 1  # only the operator row
    for table in (
        "locations",
        "memberships",
        "tenant_owners",
        "tenant_specialties",
        "subscriptions",
        "workspace_provisions",
    ):
        assert after[table] == before[table], table


# --- Idempotency ---


def test_same_key_same_payload_replays(client, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    make_owner_user(email="idem-a@example.com")
    c = login_client(client, email="idem-a@example.com")
    key = str(uuid.uuid4())
    first = _provision(c, {"slug": "idem-clinic"}, key=key)
    assert first.status_code == 201, first.text
    second = _provision(c, {"slug": "idem-clinic"}, key=key)
    assert second.status_code == 201, second.text
    assert second.json() == first.json()


def test_same_key_different_payload_is_409(client, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    make_owner_user(email="idem-b@example.com")
    c = login_client(client, email="idem-b@example.com")
    key = str(uuid.uuid4())
    assert _provision(c, {"slug": "idem-first"}, key=key).status_code == 201
    r = _provision(c, {"slug": "idem-second"}, key=key)
    assert r.status_code == 409, r.text


def test_concurrent_identical_requests_create_one_workspace(  # type: ignore[no-untyped-def]
    client, owner_db, make_owner_user
) -> None:
    make_owner_user(email="race-idem@example.com")
    key = str(uuid.uuid4())
    gate = threading.Barrier(3)
    results: list[tuple[int, str]] = []

    def attempt() -> None:
        c = TestClient(client.app, base_url="http://test")
        resp = c.post(
            "/api/v1/auth/login",
            json={"email": "race-idem@example.com", "password": "password-12345-abc"},
        )
        assert resp.status_code == 200
        gate.wait(timeout=30)
        r = c.post(
            "/api/v1/workspaces",
            json=dict(BASE_BODY, slug="race-clinic"),
            headers={"Idempotency-Key": key},
        )
        body = r.json()
        results.append((r.status_code, body.get("tenant", {}).get("id", r.text)))

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for t in threads:
        t.start()
    gate.wait(timeout=30)
    for t in threads:
        t.join(timeout=60)
    assert sorted(s for s, _ in results) == [201, 201], results
    assert results[0][1] == results[1][1]
    n = owner_db.execute(
        text("SELECT count(*) FROM tenants WHERE slug = 'race-clinic'")
    ).scalar_one()
    assert n == 1


def test_different_keys_create_independent_workspaces(  # type: ignore[no-untyped-def]
    client, make_owner_user
) -> None:
    make_owner_user(email="idem-c@example.com")
    c = login_client(client, email="idem-c@example.com")
    first = _provision(c, {"slug": "indep-one"}, key=str(uuid.uuid4()))
    second = _provision(c, {"slug": "indep-two"}, key=str(uuid.uuid4()))
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["tenant"]["id"] != second.json()["tenant"]["id"]


def test_idempotency_scoped_to_user(client, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    make_owner_user(email="idem-user-one@example.com")
    make_owner_user(email="idem-user-two@example.com")
    key = str(uuid.uuid4())
    c1 = login_client(client, email="idem-user-one@example.com")
    c2 = login_client(client, email="idem-user-two@example.com")
    first = _provision(c1, {"slug": "scoped-one"}, key=key)
    second = _provision(c2, {"slug": "scoped-two"}, key=key)
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["tenant"]["id"] != second.json()["tenant"]["id"]


# --- Authorization + isolation ---


def test_owner_has_explicit_membership(client, owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    user = make_owner_user(email="owner-j@example.com")
    c = login_client(client, email="owner-j@example.com")
    tid = _provision(c, {"slug": "member-check"}, key=str(uuid.uuid4())).json()[
        "tenant"
    ]["id"]
    members = c.get(f"/api/v1/tenants/{tid}/memberships", headers=tenant_headers(tid))
    assert members.status_code == 200, members.text
    mine = [m for m in members.json() if m["user_id"] == str(user.id)]
    assert (
        len(mine) == 1
        and mine[0]["role"] == "tenant_admin"
        and mine[0]["is_primary"] is True
    )


def test_ownership_does_not_bypass_permissions(
    client, owner_db, make_owner_user
) -> None:  # type: ignore[no-untyped-def]
    make_owner_user(email="owner-k@example.com")
    c = login_client(client, email="owner-k@example.com")
    tid = _provision(c, {"slug": "bypass-check"}, key=str(uuid.uuid4())).json()[
        "tenant"
    ]["id"]
    # Remove the membership but keep the owner row: the owner must lose access.
    owner_db.execute(text("DELETE FROM memberships WHERE tenant_id = :t"), {"t": tid})
    owner_db.commit()
    assert (
        owner_db.execute(
            text("SELECT count(*) FROM tenant_owners WHERE tenant_id = :t"), {"t": tid}
        ).scalar_one()
        == 1
    )
    r = c.get(f"/api/v1/tenants/{tid}", headers=tenant_headers(tid))
    assert r.status_code == 403, r.text


def test_one_user_owns_multiple_tenants(client, owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    user = make_owner_user(email="multi-owner@example.com")
    c = login_client(client, email="multi-owner@example.com")
    t1 = _provision(c, {"slug": "multi-one"}, key=str(uuid.uuid4())).json()["tenant"][
        "id"
    ]
    t2 = _provision(c, {"slug": "multi-two"}, key=str(uuid.uuid4())).json()["tenant"][
        "id"
    ]
    assert t1 != t2
    n = owner_db.execute(
        text("SELECT count(*) FROM tenant_owners WHERE user_id = :u"),
        {"u": str(user.id)},
    ).scalar_one()
    assert n == 2
    # Same user, valid selector for t2 but path t1: 404 anti-oracle (match_tenant).
    assert c.get(f"/api/v1/tenants/{t1}", headers=tenant_headers(t2)).status_code == 404


def test_two_users_workspaces_isolated(client, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    make_owner_user(email="iso-one@example.com")
    make_owner_user(email="iso-two@example.com")
    c1 = login_client(client, email="iso-one@example.com")
    c2 = login_client(client, email="iso-two@example.com")
    t1 = _provision(c1, {"slug": "iso-one"}, key=str(uuid.uuid4())).json()["tenant"][
        "id"
    ]
    t2 = _provision(c2, {"slug": "iso-two"}, key=str(uuid.uuid4())).json()["tenant"][
        "id"
    ]
    # Cross-tenant probes are blocked: a forged X-Tenant selector fails
    # closed in get_ctx (403 — the existing selector behavior), so no
    # tenant data is ever returned.
    assert (
        c1.get(f"/api/v1/tenants/{t2}", headers=tenant_headers(t2)).status_code == 403
    )
    assert (
        c2.get(f"/api/v1/tenants/{t1}", headers=tenant_headers(t1)).status_code == 403
    )
    mine1 = {t["id"] for t in c1.get("/api/v1/tenants/mine").json()}
    assert mine1 == {t1}


# --- RLS ---


def test_new_tables_rls_enabled_and_forced(app_factory, owner_db) -> None:  # type: ignore[no-untyped-def]
    rows = owner_db.execute(
        text(
            "SELECT tablename, rowsecurity FROM pg_tables "
            "WHERE tablename IN ('tenant_owners','subscriptions','tenant_specialties',"
            "'workspace_provisions','subscription_plans')"
        )
    ).all()
    by_name = {r[0]: r[1] for r in rows}
    for name in (
        "tenant_owners",
        "subscriptions",
        "tenant_specialties",
        "workspace_provisions",
    ):
        assert by_name.get(name) is True, name
    forced = owner_db.execute(
        text(
            "SELECT relname FROM pg_class WHERE relname IN ('tenant_owners','subscriptions',"
            "'tenant_specialties','workspace_provisions') AND relforcerowsecurity"
        )
    ).all()
    assert len(forced) == 4


def test_rls_blocks_cross_tenant_subscription_reads(  # type: ignore[no-untyped-def]
    client, app_factory, make_owner_user
) -> None:
    make_owner_user(email="rls-one@example.com")
    make_owner_user(email="rls-two@example.com")
    c1 = login_client(client, email="rls-one@example.com")
    c2 = login_client(client, email="rls-two@example.com")
    t1 = _provision(c1, {"slug": "rls-sub-one"}, key=str(uuid.uuid4())).json()[
        "tenant"
    ]["id"]
    t2 = _provision(c2, {"slug": "rls-sub-two"}, key=str(uuid.uuid4())).json()[
        "tenant"
    ]["id"]
    with app_factory() as s:
        s.execute(text("SELECT set_config('app.tenant_id', :t, false)"), {"t": t1})
        other = s.execute(
            text("SELECT count(*) FROM subscriptions WHERE tenant_id = :t"), {"t": t2}
        ).scalar_one()
        assert other == 0
        own = s.execute(
            text("SELECT count(*) FROM subscriptions WHERE tenant_id = :t"), {"t": t1}
        ).scalar_one()
        assert own == 1
        s.rollback()


def test_provision_ledger_is_user_scoped(app_factory, client, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    make_owner_user(email="ledger-one@example.com")
    make_owner_user(email="ledger-two@example.com")
    c1 = login_client(client, email="ledger-one@example.com")
    _provision(c1, {"slug": "ledger-clinic"}, key=str(uuid.uuid4()))
    u2 = make_owner_user(email="ledger-two-lookup@example.com")
    with app_factory() as s:
        s.execute(
            text("SELECT set_config('app.user_id', :u, false)"), {"u": str(u2.id)}
        )
        assert (
            s.execute(text("SELECT count(*) FROM workspace_provisions")).scalar_one()
            == 0
        )
        s.rollback()


# --- Trial ---


def test_exactly_one_14_day_trial(client, owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    make_owner_user(email="trial-a@example.com")
    c = login_client(client, email="trial-a@example.com")
    body = _provision(c, {"slug": "trial-clinic"}, key=str(uuid.uuid4())).json()
    trial_ends = datetime.fromisoformat(
        body["subscription"]["trial_ends_at"].replace("Z", "+00:00")
    )
    assert trial_ends.tzinfo is not None  # UTC timestamptz
    rows = owner_db.execute(
        text(
            "SELECT status, trial_ends_at, period_start, period_end FROM subscriptions "
            "WHERE tenant_id = :t"
        ),
        {"t": body["tenant"]["id"]},
    ).all()
    assert len(rows) == 1
    assert rows[0][0] == "trial"
    assert rows[0][1] - rows[0][2] == timedelta(days=14)
    assert rows[0][3] - rows[0][2] == timedelta(days=14)


def test_subscription_has_no_payment_columns(owner_db) -> None:  # type: ignore[no-untyped-def]
    cols = owner_db.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name IN ('subscriptions','subscription_plans')"
        )
    ).all()
    names = {r[0].lower() for r in cols}
    assert not names & {
        "card",
        "card_token",
        "payment_method",
        "charge_id",
        "gateway_customer",
    }


def test_no_trial_enforcement_on_reads(client, owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    make_owner_user(email="trial-b@example.com")
    c = login_client(client, email="trial-b@example.com")
    body = _provision(c, {"slug": "expired-trial"}, key=str(uuid.uuid4())).json()
    tid = body["tenant"]["id"]
    # Expire the trial out-of-band: reads must behave identically (no gates in O1).
    owner_db.execute(
        text(
            "UPDATE subscriptions SET trial_ends_at = now() - interval '1 day' WHERE tenant_id = :t"
        ),
        {"t": tid},
    )
    owner_db.commit()
    assert (
        c.get(f"/api/v1/tenants/{tid}", headers=tenant_headers(tid)).status_code == 200
    )
    assert (
        c.get(
            f"/api/v1/tenants/{tid}/locations", headers=tenant_headers(tid)
        ).status_code
        == 200
    )


def test_audit_and_outbox_refs_only(client, owner_db, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    make_owner_user(email="refs-only@example.com")
    c = login_client(client, email="refs-only@example.com")
    body = _provision(c, {"slug": "refs-clinic"}, key=str(uuid.uuid4())).json()
    tid = body["tenant"]["id"]
    actions = owner_db.execute(
        text("SELECT action FROM audit_events WHERE tenant_id = :t"), {"t": tid}
    ).all()
    assert {"workspace.provision", "subscription.trial.start"} <= {
        r[0] for r in actions
    }
    payloads = owner_db.execute(
        text("SELECT payload::text FROM outbox_events WHERE tenant_id = :t"), {"t": tid}
    ).all()
    assert payloads, "provisioning must enqueue the transactional outbox event"
    joined = " ".join(r[0] for r in payloads).lower()
    for forbidden in ("password", "secret", "token", "clinical", "phone", "email"):
        assert forbidden not in joined


# --- Tenant detail extension ---


def test_tenant_detail_exposes_subscription_and_specialties(  # type: ignore[no-untyped-def]
    client, make_owner_user
) -> None:
    make_owner_user(email="detail-a@example.com")
    c = login_client(client, email="detail-a@example.com")
    tid = _provision(
        c,
        {"slug": "detail-clinic", "specialty_codes": ["dental", "ophthalmology"]},
        key=str(uuid.uuid4()),
    ).json()["tenant"]["id"]
    r = c.get(f"/api/v1/tenants/{tid}", headers=tenant_headers(tid))
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["subscription"]["status"] == "trial"
    assert detail["subscription"]["plan_code"] == "trial-14d"
    assert detail["subscription"]["trial_ends_at"]
    assert sorted(detail["specialties_enabled"]) == ["dental", "ophthalmology"]


def test_legacy_tenant_detail_has_no_subscription(
    client, owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from app.modules.clinics import service as clinics_service
    from app.modules.tenancy import service as tenancy_service

    admin = make_owner_user(email="legacy-admin@example.com")
    tenant = make_tenant(slug="legacy-tenant")
    clinics_service.create_location(owner_db, tenant=tenant, name="HQ")
    tenancy_service.create_membership(
        owner_db,
        user=admin,
        tenant=tenant,
        role=tenancy_service.get_seed_role(owner_db, "tenant_admin"),
        is_primary=True,
    )
    owner_db.commit()
    c = login_client(client, email="legacy-admin@example.com")
    r = c.get(f"/api/v1/tenants/{tenant.id}", headers=tenant_headers(str(tenant.id)))
    assert r.status_code == 200, r.text
    assert r.json()["subscription"] is None
    assert r.json()["specialties_enabled"] == []
