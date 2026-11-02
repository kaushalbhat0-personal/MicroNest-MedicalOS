"""Scheduling domain: validation, lifecycle, timezone, overlap, idempotency.

Service-level (owner session, no HTTP): proves the domain rules themselves.
API/isolation behavior is covered in tests/api + tests/isolation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.modules.scheduling import models as M
from app.modules.scheduling import service as sched
from app.platform.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.platform.time import UTC
from tests.helpers import provision_scheduling

NY = ZoneInfo("America/New_York")
KOLKATA = ZoneInfo("Asia/Kolkata")


def _future_utc(*, days: int = 2, hour: int = 10, minute: int = 0) -> datetime:
    base = datetime.now(UTC) + timedelta(days=days)
    return base.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _book(db, bundle, **kw):  # type: ignore[no-untyped-def]
    tenant = bundle["tenant"]
    args = {
        "tenant_id": tenant.id,
        "actor_id": bundle["admin"].id,
        "patient_id": bundle["patient"].id,
        "practitioner_id": bundle["practitioner"].id,
        "location_id": bundle["location"].id,
        "start": _future_utc(),
        "duration_minutes": 30,
    }
    args.update(kw)
    return sched.create_appointment(db, **args)  # type: ignore[arg-type]


def test_create_persists_utc_instant(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_scheduling(owner_db, make_owner_user, make_tenant)
    start = _future_utc().astimezone(KOLKATA)  # aware, non-UTC offset
    appt = _book(owner_db, b, start=start)
    assert appt.start_at.tzinfo is not None
    assert appt.start_at == start.astimezone(UTC)
    assert appt.end_at == appt.start_at + timedelta(minutes=30)
    assert appt.status == M.STATUS_SCHEDULED


def test_naive_start_uses_location_timezone(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_scheduling(owner_db, make_owner_user, make_tenant)
    wall = (_future_utc().astimezone(KOLKATA)).replace(tzinfo=None)
    appt = _book(owner_db, b, start=wall)
    assert appt.start_at == wall.replace(tzinfo=KOLKATA, fold=0).astimezone(UTC)
    assert appt.timezone == "Asia/Kolkata"


def test_explicit_timezone_overrides_location(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_scheduling(owner_db, make_owner_user, make_tenant)
    wall = (_future_utc().astimezone(NY)).replace(tzinfo=None)
    appt = _book(owner_db, b, start=wall, timezone_name="America/New_York")
    assert appt.timezone == "America/New_York"
    assert appt.start_at == wall.replace(tzinfo=NY, fold=0).astimezone(UTC)


def test_unknown_timezone_rejected(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_scheduling(owner_db, make_owner_user, make_tenant)
    with pytest.raises(ValidationError):
        _book(owner_db, b, start=_future_utc(), timezone_name="Mars/Olympus")


def _first_sunday(year: int, month: int, ordinal: int) -> int:
    from datetime import date

    d = date(year, month, 1)
    shift = (6 - d.weekday()) % 7  # days to first Sunday
    return 1 + shift + 7 * (ordinal - 1)


def _ny_transition_wall(kind: str) -> datetime:
    """Next future ambiguous (fall-back) or non-existent (spring-forward)
    wall-clock time in America/New_York, so DST tests never rot."""
    now = datetime.now(UTC)
    for year in (now.year, now.year + 1, now.year + 2):
        if kind == "ambiguous":
            day = _first_sunday(year, 11, 1)
            cand = datetime(year, 11, day, 1, 30)
        else:
            day = _first_sunday(year, 3, 2)
            cand = datetime(year, 3, day, 2, 30)
        if cand.replace(tzinfo=NY, fold=0).astimezone(UTC) > now + timedelta(days=1):
            return cand
    raise AssertionError("no future DST transition found")


def test_dst_ambiguous_wall_time_uses_fold_zero(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_scheduling(owner_db, make_owner_user, make_tenant)
    wall = _ny_transition_wall("ambiguous")
    appt = _book(owner_db, b, start=wall, timezone_name="America/New_York")
    # fold=0 = first occurrence (EDT, UTC-4), deterministic and documented.
    assert appt.start_at == wall.replace(tzinfo=NY, fold=0).astimezone(UTC)


def test_dst_gap_wall_time_rejected(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_scheduling(owner_db, make_owner_user, make_tenant)
    wall = _ny_transition_wall("gap")
    with pytest.raises(ValidationError):
        _book(owner_db, b, start=wall, timezone_name="America/New_York")


def test_start_must_be_future(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_scheduling(owner_db, make_owner_user, make_tenant)
    with pytest.raises(ValidationError):
        _book(owner_db, b, start=datetime.now(UTC) - timedelta(hours=1))


def test_end_must_be_after_start_rejected_by_duration(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_scheduling(owner_db, make_owner_user, make_tenant)
    with pytest.raises(ValidationError):
        _book(owner_db, b, duration_minutes=0)


@pytest.mark.parametrize(
    "to_status", ["confirmed", "checked_in", "cancelled", "no_show"]
)
def test_valid_transitions_from_scheduled(
    owner_db, make_owner_user, make_tenant, to_status: str
) -> None:  # type: ignore[no-untyped-def]
    b = provision_scheduling(owner_db, make_owner_user, make_tenant)
    appt = _book(owner_db, b)
    out = sched.transition_appointment(
        owner_db, tenant_id=b["tenant"].id, appointment_id=appt.id, to_status=to_status
    )
    assert out.status == to_status


def test_full_happy_path_lifecycle(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_scheduling(owner_db, make_owner_user, make_tenant)
    appt = _book(owner_db, b)
    tid = b["tenant"].id
    for nxt in ("confirmed", "checked_in", "completed"):
        appt = sched.transition_appointment(
            owner_db, tenant_id=tid, appointment_id=appt.id, to_status=nxt
        )
    assert appt.status == M.STATUS_COMPLETED


def test_invalid_transition_rejected(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_scheduling(owner_db, make_owner_user, make_tenant)
    appt = _book(owner_db, b)
    with pytest.raises(ValidationError):
        sched.transition_appointment(
            owner_db,
            tenant_id=b["tenant"].id,
            appointment_id=appt.id,
            to_status="completed",
        )


def test_terminal_states_are_final(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_scheduling(owner_db, make_owner_user, make_tenant)
    appt = _book(owner_db, b)
    tid = b["tenant"].id
    sched.transition_appointment(
        owner_db, tenant_id=tid, appointment_id=appt.id, to_status="cancelled"
    )
    with pytest.raises(ValidationError):
        sched.transition_appointment(
            owner_db, tenant_id=tid, appointment_id=appt.id, to_status="scheduled"
        )


def test_same_state_transition_is_idempotent_noop(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_scheduling(owner_db, make_owner_user, make_tenant)
    appt = _book(owner_db, b)
    same = sched.transition_appointment(
        owner_db,
        tenant_id=b["tenant"].id,
        appointment_id=appt.id,
        to_status="scheduled",
    )
    assert same.id == appt.id
    assert same.status == "scheduled"


def test_cancel_records_metadata(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_scheduling(owner_db, make_owner_user, make_tenant)
    appt = _book(owner_db, b)
    out = sched.cancel_appointment(
        owner_db,
        tenant_id=b["tenant"].id,
        appointment_id=appt.id,
        actor_id=b["admin"].id,
        reason="patient request",
    )
    assert out.status == M.STATUS_CANCELLED
    assert out.cancelled_at is not None
    assert out.cancelled_by == b["admin"].id
    assert out.cancel_reason == "patient request"


def test_reschedule_moves_window(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_scheduling(owner_db, make_owner_user, make_tenant)
    appt = _book(owner_db, b)
    new_start = _future_utc(days=5)
    out = sched.reschedule_appointment(
        owner_db,
        tenant_id=b["tenant"].id,
        appointment_id=appt.id,
        start=new_start,
        duration_minutes=45,
    )
    assert out.start_at == new_start
    assert out.end_at == new_start + timedelta(minutes=45)


def test_reschedule_terminal_rejected(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_scheduling(owner_db, make_owner_user, make_tenant)
    appt = _book(owner_db, b)
    tid = b["tenant"].id
    sched.transition_appointment(
        owner_db, tenant_id=tid, appointment_id=appt.id, to_status="no_show"
    )
    with pytest.raises(ValidationError):
        sched.reschedule_appointment(
            owner_db,
            tenant_id=tid,
            appointment_id=appt.id,
            start=_future_utc(days=6),
            duration_minutes=30,
        )


def test_overlap_conflicts_same_practitioner(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_scheduling(owner_db, make_owner_user, make_tenant)
    start = _future_utc()
    _book(owner_db, b, start=start)
    with pytest.raises(ConflictError):
        _book(owner_db, b, start=start + timedelta(minutes=15))


def test_adjacent_slots_do_not_conflict(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_scheduling(owner_db, make_owner_user, make_tenant)
    start = _future_utc()
    _book(owner_db, b, start=start)
    second = _book(owner_db, b, start=start + timedelta(minutes=30))
    assert second.start_at == start + timedelta(minutes=30)


def test_cancelled_slot_frees_practitioner(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_scheduling(owner_db, make_owner_user, make_tenant)
    start = _future_utc()
    appt = _book(owner_db, b, start=start)
    sched.cancel_appointment(
        owner_db,
        tenant_id=b["tenant"].id,
        appointment_id=appt.id,
        actor_id=b["admin"].id,
    )
    owner_db.commit()
    again = _book(owner_db, b, start=start)
    assert again.id != appt.id


def test_reschedule_into_occupied_slot_conflicts(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_scheduling(owner_db, make_owner_user, make_tenant)
    first = _book(owner_db, b, start=_future_utc())
    second = _book(owner_db, b, start=_future_utc(days=3))
    with pytest.raises(ConflictError):
        sched.reschedule_appointment(
            owner_db,
            tenant_id=b["tenant"].id,
            appointment_id=second.id,
            start=first.start_at,
            duration_minutes=30,
        )


def test_create_idempotent_on_key(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_scheduling(owner_db, make_owner_user, make_tenant)
    start = _future_utc()
    key = f"key-{uuid.uuid4().hex}"
    first = _book(owner_db, b, start=start, idempotency_key=key)
    owner_db.commit()
    # Same params replayed (new session state): same row, no duplicate.
    second = _book(owner_db, b, start=start, idempotency_key=key)
    assert second.id == first.id


def test_idempotency_key_mismatch_conflicts(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_scheduling(owner_db, make_owner_user, make_tenant)
    key = f"key-{uuid.uuid4().hex}"
    _book(owner_db, b, start=_future_utc(), idempotency_key=key)
    owner_db.commit()
    with pytest.raises(ConflictError):
        _book(owner_db, b, start=_future_utc(days=4), idempotency_key=key)


def test_unverified_practitioner_rejected(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from app.modules.tenancy import service as tenancy_service

    b = provision_scheduling(owner_db, make_owner_user, make_tenant)
    rogue = tenancy_service.register_practitioner(owner_db, display_name="Rogue")
    owner_db.commit()
    with pytest.raises((ForbiddenError, NotFoundError)):
        _book(owner_db, b, practitioner_id=rogue.id)


def test_cross_tenant_refs_rejected(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    from tests.helpers import provision_tenant

    a = provision_scheduling(owner_db, make_owner_user, make_tenant, slug="sched-a")
    other = provision_tenant(owner_db, make_owner_user, make_tenant, slug="sched-b")
    with pytest.raises(NotFoundError):
        _book(
            owner_db,
            a,
            patient_id=other["admin"].id,  # not even a patient: must fail closed
        )
    # Another tenant's location id against our tenant: 404, never cross-write.
    with pytest.raises(NotFoundError):
        _book(owner_db, a, location_id=other["location"].id)


def test_location_scope_enforced(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_scheduling(owner_db, make_owner_user, make_tenant)
    with pytest.raises(ForbiddenError):
        sched.create_appointment(
            owner_db,
            tenant_id=b["tenant"].id,
            actor_id=b["admin"].id,
            patient_id=b["patient"].id,
            practitioner_id=b["practitioner"].id,
            location_id=b["location"].id,
            start=_future_utc(),
            duration_minutes=30,
            location_ids=frozenset({uuid.uuid4()}),
        )
