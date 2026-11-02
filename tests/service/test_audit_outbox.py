"""Audit append/chain + outbox emit/claim/retry/dead + rollback atomicity."""

import pytest
from sqlalchemy import text

from app.modules.audit import service as audit_service
from app.platform.events import service as outbox_service
from app.platform.events.outbox import DEAD


def _tenant(owner_db, make_tenant):  # type: ignore[no-untyped-def]
    t = make_tenant()
    return t


def test_audit_append_and_chain(owner_db, make_tenant) -> None:  # type: ignore[no-untyped-def]
    t = _tenant(owner_db, make_tenant)
    for i in range(3):
        audit_service.append(
            owner_db,
            tenant_id=t.id,
            actor_type="user",
            actor_id="u-1",
            action=f"test.{i}",
            resource_type="tenant",
            resource_id=str(t.id),
        )
    owner_db.commit()
    from datetime import datetime, timezone

    day = datetime.now(timezone.utc).date().isoformat()
    assert audit_service.verify_chain(owner_db, tenant_id=t.id, day=day)


def test_audit_chain_detects_tamper(owner_db, make_tenant) -> None:  # type: ignore[no-untyped-def]
    t = _tenant(owner_db, make_tenant)
    e = audit_service.append(
        owner_db,
        tenant_id=t.id,
        actor_type="user",
        actor_id="u-1",
        action="test.x",
        resource_type="tenant",
        resource_id=str(t.id),
    )
    owner_db.commit()
    owner_db.execute(
        text("UPDATE audit_events SET action='forged' WHERE id=:i"), {"i": str(e.id)}
    )
    owner_db.commit()
    owner_db.expunge_all()
    from datetime import datetime, timezone

    day = datetime.now(timezone.utc).date().isoformat()
    assert not audit_service.verify_chain(owner_db, tenant_id=t.id, day=day)


def test_audit_forbids_update_delete_for_app(app_factory, owner_db) -> None:  # type: ignore[no-untyped-def]
    tid = "00000000-0000-7000-8000-000000000001"
    with app_factory() as s:
        s.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tid})
        row = s.execute(
            text(
                "INSERT INTO audit_events (id, occurred_at, tenant_id, actor_type, actor_id, action, resource_type, resource_id, result, chain_day, prev_hash, event_hash) VALUES (gen_random_uuid(), now(), CAST(:t AS uuid), 'user', 'u', 'a', 'r', 'r', 'ok', '2000-01-01', 'x', 'y') RETURNING id"
            ),
            {"t": tid},
        ).fetchone()
        assert row is not None
        s.commit()
    # UPDATE and DELETE have no policy and the privilege is revoked: both fail.
    with app_factory() as s2:
        s2.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tid})
        with pytest.raises(Exception):
            s2.execute(
                text("UPDATE audit_events SET action='z' WHERE id=:i"),
                {"i": str(row[0])},
            )
            s2.commit()
        s2.rollback()
        with pytest.raises(Exception):
            s2.execute(text("DELETE FROM audit_events WHERE id=:i"), {"i": str(row[0])})
            s2.commit()


def test_outbox_rollback_atomicity(owner_db, make_tenant) -> None:  # type: ignore[no-untyped-def]
    t = _tenant(owner_db, make_tenant)
    outbox_service.emit(
        owner_db,
        type="test.evt",
        aggregate="t",
        aggregate_id="1",
        tenant_id=t.id,
        payload={"ref": "1"},
    )
    owner_db.rollback()
    claimed = outbox_service.claim_batch(owner_db)
    assert [e for e in claimed if e.aggregate_id == "1"] == []


def test_outbox_retry_then_dead(owner_db, make_tenant) -> None:  # type: ignore[no-untyped-def]
    t = _tenant(owner_db, make_tenant)
    outbox_service.emit(
        owner_db,
        type="no.such.handler",
        aggregate="t",
        aggregate_id="dead-1",
        tenant_id=t.id,
        payload={"ref": "1"},
    )
    owner_db.commit()
    from app.platform.events import outbox as models

    for _ in range(models.MAX_ATTEMPTS + 2):
        # Force the event due with a 1s margin: DB now() and any client clock
        # must never be compared at microsecond precision (see claim_batch).
        owner_db.execute(
            text(
                "UPDATE outbox_events SET next_attempt_at = now() - interval '1 second' WHERE status='failed'"
            )
        )
        owner_db.commit()
        outbox_service.process_batch(owner_db, handlers={})
    owner_db.commit()
    row = owner_db.execute(
        text("SELECT status FROM outbox_events WHERE aggregate_id='dead-1'")
    ).scalar_one()
    assert row == DEAD


def test_outbox_success_path(owner_db, make_tenant) -> None:  # type: ignore[no-untyped-def]
    t = _tenant(owner_db, make_tenant)
    seen = []
    outbox_service.emit(
        owner_db,
        type="test.ok",
        aggregate="t",
        aggregate_id="ok-1",
        tenant_id=t.id,
        payload={"ref": "1"},
    )
    owner_db.commit()
    done = outbox_service.process_batch(
        owner_db, handlers={"test.ok": lambda e: seen.append(e.id)}
    )
    assert done["sent"] == 1 and seen
