"""Estimate domain: lifecycle, snapshots, totals, scope, idempotency."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from app.modules.billing import estimates as est
from app.modules.billing import models as M
from app.modules.billing import service_catalog as catalog
from app.platform.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from tests.helpers import provision_clinical


def _open_encounter(owner_db, b):  # type: ignore[no-untyped-def]
    from app.modules.clinical import service as enc

    return enc.open_encounter(
        owner_db,
        tenant_id=b["tenant"].id,
        actor_id=b["admin"].id,
        patient_id=b["patient"].id,
        practitioner_id=b["practitioner"].id,
        location_id=b["location"].id,
    )


def _ids(b):  # type: ignore[no-untyped-def]
    return {
        "tenant_id": b["tenant"].id,
        "location_id": b["location"].id,
        "patient_id": b["patient"].id,
    }


def _create(owner_db, b, **kw):  # type: ignore[no-untyped-def]
    args = {"actor_id": b["admin"].id, **_ids(b)}
    args.update(kw)
    return est.create_estimate(owner_db, **args)


def test_create_computes_totals(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    item = catalog.create_service(
        owner_db,
        code=f"ct-{uuid.uuid4().hex[:6]}",
        display="Filling",
        default_rate="200.00",
    )
    e = _create(
        owner_db,
        b,
        items=[
            {
                "service_catalog_id": item.id,
                "quantity": 2,
                "discount_amount": "10.00",
                "tax_rate": "18",
            }
        ],
    )
    assert e.status == M.ESTIMATE_DRAFT
    lines = est.estimate_lines(owner_db, estimate_id=e.id)
    assert len(lines) == 1
    assert str(lines[0].taxable_amount) == "390.00"
    assert str(lines[0].tax_amount) == "70.20"
    assert str(lines[0].line_total) == "460.20"
    assert str(e.subtotal) == "390.00"
    assert str(e.tax_total) == "70.20"
    assert str(e.grand_total) == "460.20"


def test_catalog_snapshot_is_mandatory_regression(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    """Catalog rate/tax edits after line creation must not move the snapshot."""
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    item = catalog.create_service(
        owner_db,
        code=f"snap-{uuid.uuid4().hex[:6]}",
        display="Crown",
        default_rate="1000.00",
        tax_rate="18",
        hsn_sac="9983",
    )
    e = _create(owner_db, b, items=[{"service_catalog_id": item.id, "quantity": 1}])
    before_total = str(e.grand_total)
    catalog.update_service(
        owner_db, item_id=item.id, default_rate="9999.00", tax_rate="28"
    )
    owner_db.expire_all()
    from decimal import Decimal

    lines = est.estimate_lines(owner_db, estimate_id=e.id)
    assert lines[0].unit_rate == Decimal("1000.00")
    assert lines[0].tax_rate == Decimal("18")
    assert lines[0].line_total == Decimal("1180.00")
    reloaded = est.get_estimate(owner_db, tenant_id=b["tenant"].id, estimate_id=e.id)
    assert reloaded.grand_total == Decimal(before_total) == Decimal("1180.00")


def test_inactive_catalog_blocked_for_new_lines(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    item = catalog.create_service(
        owner_db, code=f"ina-{uuid.uuid4().hex[:6]}", display="X", default_rate="10.00"
    )
    catalog.set_active(owner_db, item_id=item.id, is_active=False)
    with pytest.raises(ValidationError):
        _create(owner_db, b, items=[{"service_catalog_id": item.id, "quantity": 1}])
    e = _create(
        owner_db,
        b,
        items=[{"description": "free text", "quantity": 1, "unit_rate": "5"}],
    )
    with pytest.raises(ValidationError):
        est.add_estimate_line(
            owner_db,
            tenant_id=b["tenant"].id,
            estimate_id=e.id,
            service_catalog_id=item.id,
        )


def test_draft_editing_recomputes_and_versions(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    e = _create(
        owner_db, b, items=[{"description": "a", "quantity": 1, "unit_rate": "100.00"}]
    )
    v0 = e.version
    line2 = est.add_estimate_line(
        owner_db,
        tenant_id=b["tenant"].id,
        estimate_id=e.id,
        description="b",
        quantity=2,
        unit_rate="50.00",
    )
    assert str(e.grand_total) == "200.00"
    assert e.version == v0 + 1
    est.update_estimate_line(
        owner_db, tenant_id=b["tenant"].id, line_id=line2.id, quantity=1
    )
    assert str(e.grand_total) == "150.00"
    est.remove_estimate_line(owner_db, tenant_id=b["tenant"].id, line_id=line2.id)
    assert str(e.grand_total) == "100.00"
    assert len(est.estimate_lines(owner_db, estimate_id=e.id)) == 1


def test_issue_freezes_content(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    e = _create(
        owner_db, b, items=[{"description": "a", "quantity": 1, "unit_rate": "100.00"}]
    )
    issued = est.issue_estimate(
        owner_db, tenant_id=b["tenant"].id, estimate_id=e.id, actor_id=b["admin"].id
    )
    assert issued.status == M.ESTIMATE_ISSUED
    assert issued.issued_by == b["admin"].id
    assert issued.issued_at is not None
    # Same-state re-issue is a no-op success per repository convention.
    assert (
        est.issue_estimate(
            owner_db, tenant_id=b["tenant"].id, estimate_id=e.id, actor_id=b["admin"].id
        ).status
        == M.ESTIMATE_ISSUED
    )
    with pytest.raises(ConflictError):
        est.update_estimate(
            owner_db, tenant_id=b["tenant"].id, estimate_id=e.id, notes="x"
        )
    with pytest.raises(ConflictError):
        est.add_estimate_line(
            owner_db, tenant_id=b["tenant"].id, estimate_id=e.id, description="b"
        )
    line = est.estimate_lines(owner_db, estimate_id=e.id)[0]
    with pytest.raises(ConflictError):
        est.update_estimate_line(
            owner_db, tenant_id=b["tenant"].id, line_id=line.id, quantity=2
        )
    with pytest.raises(ConflictError):
        est.remove_estimate_line(owner_db, tenant_id=b["tenant"].id, line_id=line.id)
    # Terminal-transition attempts on frozen content also conflict.
    with pytest.raises(ConflictError):
        est.expire_estimate(owner_db, tenant_id=b["tenant"].id, estimate_id=e.id)
        est.cancel_estimate(owner_db, tenant_id=b["tenant"].id, estimate_id=e.id)


def test_cancel_expire_and_terminal_rules(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    tid = b["tenant"].id
    e1 = _create(owner_db, b)
    assert (
        est.cancel_estimate(owner_db, tenant_id=tid, estimate_id=e1.id).status
        == "cancelled"
    )
    # Same-state cancel is a no-op success.
    assert (
        est.cancel_estimate(owner_db, tenant_id=tid, estimate_id=e1.id).status
        == "cancelled"
    )
    with pytest.raises(ConflictError):
        est.issue_estimate(
            owner_db, tenant_id=tid, estimate_id=e1.id, actor_id=b["admin"].id
        )
    e2 = _create(owner_db, b)
    est.issue_estimate(
        owner_db, tenant_id=tid, estimate_id=e2.id, actor_id=b["admin"].id
    )
    assert (
        est.expire_estimate(owner_db, tenant_id=tid, estimate_id=e2.id).status
        == "expired"
    )
    with pytest.raises(ConflictError):
        est.cancel_estimate(owner_db, tenant_id=tid, estimate_id=e2.id)
    e3 = _create(owner_db, b)
    with pytest.raises(ConflictError):
        est.expire_estimate(
            owner_db, tenant_id=tid, estimate_id=e3.id
        )  # draft cannot expire
    with pytest.raises(ValidationError):
        est.transition_estimate(
            owner_db, tenant_id=tid, estimate_id=e3.id, to_status="bogus"
        )


def test_past_valid_until_blocks_issue(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    e = _create(owner_db, b, valid_until=date.today() - timedelta(days=1))
    with pytest.raises(ValidationError):
        est.issue_estimate(
            owner_db, tenant_id=b["tenant"].id, estimate_id=e.id, actor_id=b["admin"].id
        )


def test_tenant_patient_encounter_integrity(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from app.modules.patients import service as patients_service

    a = provision_clinical(owner_db, make_owner_user, make_tenant, slug="est-int-a")
    c = provision_clinical(owner_db, make_owner_user, make_tenant, slug="est-int-b")
    other = patients_service.register_patient(
        owner_db, tenant_id=a["tenant"].id, display_name="Other"
    )
    owner_db.flush()
    # Cross-tenant patient reference is a 404 oracle miss.
    with pytest.raises(NotFoundError):
        _create(owner_db, a, patient_id=c["patient"].id)
    enc = _open_encounter(owner_db, a)
    # Encounter bound to another patient is rejected.
    with pytest.raises(ValidationError):
        _create(
            owner_db,
            a,
            patient_id=other.id,
            encounter_id=enc.id,
            location_id=a["location"].id,
        )
    # Estimate location must match the encounter location.
    from app.modules.clinics import service as clinics_service

    loc2 = clinics_service.create_location(owner_db, tenant=a["tenant"], name="Annex")
    owner_db.flush()
    with pytest.raises(ValidationError):
        _create(owner_db, a, encounter_id=enc.id, location_id=loc2.id)
    # Valid encounter linkage works and records the plan-agnostic reference.
    plan_id = uuid.uuid4()  # opaque dental reference: stored, never dereferenced
    ok = _create(
        owner_db,
        a,
        encounter_id=enc.id,
        location_id=a["location"].id,
        treatment_plan_id=plan_id,
    )
    assert ok.encounter_id == enc.id
    assert ok.treatment_plan_id == plan_id


def test_location_scope_fail_closed(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    import uuid as _uuid

    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    scope = frozenset({_uuid.uuid4()})
    with pytest.raises(ForbiddenError):
        _create(owner_db, b, location_ids=scope)
    e = _create(owner_db, b)
    with pytest.raises(ForbiddenError):
        est.get_estimate(
            owner_db, tenant_id=b["tenant"].id, estimate_id=e.id, location_ids=scope
        )
    enc = _open_encounter(owner_db, b)
    linked = _create(owner_db, b, encounter_id=enc.id, location_id=b["location"].id)
    with pytest.raises(ForbiddenError):
        est.get_estimate(
            owner_db,
            tenant_id=b["tenant"].id,
            estimate_id=linked.id,
            location_ids=scope,
        )


def test_idempotency_replay_and_divergence(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    first = _create(owner_db, b, idempotency_key="est-key-1")
    replay = _create(owner_db, b, idempotency_key="est-key-1")
    assert replay.id == first.id
    from app.modules.patients import service as patients_service

    other = patients_service.register_patient(
        owner_db, tenant_id=b["tenant"].id, display_name="Divergent"
    )
    owner_db.flush()
    with pytest.raises(ConflictError):
        _create(owner_db, b, patient_id=other.id, idempotency_key="est-key-1")


def test_unverified_practitioner_rejected(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from app.modules.tenancy import service as tenancy_service

    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    rogue = tenancy_service.register_practitioner(owner_db, display_name="Rogue Bill")
    owner_db.flush()
    with pytest.raises(ForbiddenError):
        _create(owner_db, b, practitioner_id=rogue.id)
