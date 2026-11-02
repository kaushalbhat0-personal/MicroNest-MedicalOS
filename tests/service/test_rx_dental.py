"""Prescription + dental domain: lifecycles, validation, corrections,
FDI rules, consents, recalls, document references. Service-level."""

from __future__ import annotations

from datetime import date

import pytest

from app.modules.clinical import records as rec
from app.modules.clinical import service as enc
from app.modules.dental import models as DM
from app.modules.dental import plans as dplans
from app.modules.dental import service as dental
from app.modules.prescriptions import models as PM
from app.modules.prescriptions import service as rx
from app.platform.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from tests.helpers import provision_clinical


def _open(db, b):  # type: ignore[no-untyped-def]
    return enc.open_encounter(
        db,
        tenant_id=b["tenant"].id,
        actor_id=b["admin"].id,
        patient_id=b["patient"].id,
        practitioner_id=b["practitioner"].id,
        location_id=b["location"].id,
    )


def _rx_items(**kw):  # type: ignore[no-untyped-def]
    item = {
        "medication_code": "paracetamol-650",
        "dose": "650 mg",
        "route": "oral",
        "frequency": "TID",
        "instructions": "after food",
    }
    item.update(kw)
    return [item]


def test_prescription_sign_and_correct(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    e = _open(owner_db, b)
    tid = b["tenant"].id
    p = rx.create_prescription(
        owner_db,
        tenant_id=tid,
        encounter_id=e.id,
        prescribed_by=b["practitioner"].id,
        items=_rx_items(),
    )
    assert p.status == PM.RX_DRAFT
    with pytest.raises(ForbiddenError):
        rx.sign_prescription(
            owner_db, tenant_id=tid, prescription_id=p.id, actor_id=b["admin"].id
        )
    signed = rx.sign_prescription(
        owner_db, tenant_id=tid, prescription_id=p.id, actor_id=b["practitioner"].id
    )
    assert signed.status == PM.RX_SIGNED
    assert signed.signed_by == b["practitioner"].id
    with pytest.raises(ConflictError):
        rx.sign_prescription(
            owner_db, tenant_id=tid, prescription_id=p.id, actor_id=b["practitioner"].id
        )
    corrected = rx.correct_prescription(
        owner_db,
        tenant_id=tid,
        prescription_id=p.id,
        prescribed_by=b["practitioner"].id,
        items=_rx_items(frequency="BID"),
    )
    assert corrected.status == PM.RX_DRAFT
    assert corrected.version == 2
    assert corrected.supersedes_id == p.id
    old = rx.get_prescription(owner_db, tenant_id=tid, prescription_id=p.id)
    assert old.superseded_by_id == corrected.id
    assert old.status == PM.RX_SIGNED  # signed history untouched


def test_prescription_cancel_is_idempotent_retry(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    e = _open(owner_db, b)
    tid = b["tenant"].id
    p = rx.create_prescription(
        owner_db,
        tenant_id=tid,
        encounter_id=e.id,
        prescribed_by=b["practitioner"].id,
        items=_rx_items(),
    )
    c1 = rx.cancel_prescription(
        owner_db,
        tenant_id=tid,
        prescription_id=p.id,
        actor_id=b["practitioner"].id,
        reason="duplicate",
    )
    assert c1.status == PM.RX_CANCELLED
    c2 = rx.cancel_prescription(
        owner_db, tenant_id=tid, prescription_id=p.id, actor_id=b["practitioner"].id
    )
    assert c2.id == p.id


def test_unknown_medication_rejected(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    e = _open(owner_db, b)
    with pytest.raises(ValidationError):
        rx.create_prescription(
            owner_db,
            tenant_id=b["tenant"].id,
            encounter_id=e.id,
            prescribed_by=b["practitioner"].id,
            items=_rx_items(medication_code="nope"),
        )


def test_fdi_validation(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    e = _open(owner_db, b)
    tid = b["tenant"].id
    for tooth in (11, 18, 21, 28, 31, 38, 41, 48, 16, 26, 36, 46):
        f = dental.record_finding(
            owner_db,
            tenant_id=tid,
            encounter_id=e.id,
            practitioner_id=b["practitioner"].id,
            tooth=tooth,
            condition_code="caries",
        )
        assert f.tooth == tooth
    for bad in (0, 9, 19, 29, 39, 49, 51, 85, 99, 100):
        with pytest.raises(ValidationError):
            dental.record_finding(
                owner_db,
                tenant_id=tid,
                encounter_id=e.id,
                practitioner_id=b["practitioner"].id,
                tooth=bad,
                condition_code="caries",
            )
    with pytest.raises(ValidationError):
        dental.record_finding(
            owner_db,
            tenant_id=tid,
            encounter_id=e.id,
            practitioner_id=b["practitioner"].id,
            tooth=16,
            condition_code="caries",
            surfaces=["mesial", "mesial"],
        )
    with pytest.raises(ValidationError):
        dental.record_finding(
            owner_db,
            tenant_id=tid,
            encounter_id=e.id,
            practitioner_id=b["practitioner"].id,
            tooth=16,
            condition_code="caries",
            surfaces=["tentacle"],
        )


def test_finding_resolve_and_surfaces(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    e = _open(owner_db, b)
    tid = b["tenant"].id
    f = dental.record_finding(
        owner_db,
        tenant_id=tid,
        encounter_id=e.id,
        practitioner_id=b["practitioner"].id,
        tooth=16,
        condition_code="caries",
        surfaces=["Mesial", "Occlusal"],
        details="deep",
    )
    assert dental.finding_surfaces(owner_db, finding_id=f.id) == ["mesial", "occlusal"]
    resolved = dental.resolve_finding(owner_db, tenant_id=tid, finding_id=f.id)
    assert resolved.status == DM.FINDING_RESOLVED
    with pytest.raises(ConflictError):
        dental.resolve_finding(owner_db, tenant_id=tid, finding_id=f.id)


def test_plan_lifecycle_with_items(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    e = _open(owner_db, b)
    tid = b["tenant"].id
    plan = dplans.create_plan(
        owner_db,
        tenant_id=tid,
        actor_id=b["admin"].id,
        patient_id=b["patient"].id,
        practitioner_id=b["practitioner"].id,
        encounter_id=e.id,
        notes="full mouth rehab",
    )
    assert plan.status == DM.PLAN_DRAFT
    with pytest.raises(ValidationError):
        dplans.activate_plan(owner_db, tenant_id=tid, plan_id=plan.id)
    item = dplans.add_plan_item(
        owner_db,
        tenant_id=tid,
        plan_id=plan.id,
        procedure_code="filling",
        tooth=16,
        surface="occlusal",
        sequence=1,
    )
    assert item.status == DM.ITEM_PROPOSED
    active = dplans.activate_plan(owner_db, tenant_id=tid, plan_id=plan.id)
    assert active.status == DM.PLAN_ACTIVE
    assert active.version == 2
    with pytest.raises(ConflictError):
        dplans.add_plan_item(
            owner_db,
            tenant_id=tid,
            plan_id=plan.id,
            procedure_code="cleaning",
            sequence=2,
        )
    with pytest.raises(ConflictError):
        dplans.complete_plan(owner_db, tenant_id=tid, plan_id=plan.id)
    dplans.transition_plan_item(
        owner_db, tenant_id=tid, item_id=item.id, to_status="planned"
    )
    moved = dplans.transition_plan_item(
        owner_db, tenant_id=tid, item_id=item.id, to_status="in_progress"
    )
    done = dplans.transition_plan_item(
        owner_db, tenant_id=tid, item_id=moved.id, to_status="completed"
    )
    assert done.status == DM.ITEM_COMPLETED
    with pytest.raises(ValidationError):
        dplans.transition_plan_item(
            owner_db, tenant_id=tid, item_id=item.id, to_status="planned"
        )
    completed = dplans.complete_plan(owner_db, tenant_id=tid, plan_id=plan.id)
    assert completed.status == DM.PLAN_COMPLETED


def test_procedure_record_lifecycle(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    e = _open(owner_db, b)
    tid = b["tenant"].id
    r = dplans.record_procedure(
        owner_db,
        tenant_id=tid,
        encounter_id=e.id,
        practitioner_id=b["practitioner"].id,
        procedure_code="filling",
        tooth=16,
        surface="occlusal",
    )
    assert r.status == DM.RECORD_PLANNED
    started = dplans.transition_procedure_record(
        owner_db, tenant_id=tid, record_id=r.id, to_status="in_progress"
    )
    done = dplans.transition_procedure_record(
        owner_db, tenant_id=tid, record_id=started.id, to_status="completed"
    )
    assert done.status == DM.RECORD_COMPLETED
    assert done.performed_at is not None
    with pytest.raises(ValidationError):
        dplans.transition_procedure_record(
            owner_db, tenant_id=tid, record_id=r.id, to_status="planned"
        )


def test_consent_single_subject_and_withdraw(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    tid = b["tenant"].id
    plan = dplans.create_plan(
        owner_db,
        tenant_id=tid,
        actor_id=b["admin"].id,
        patient_id=b["patient"].id,
        practitioner_id=b["practitioner"].id,
    )
    with pytest.raises(ValidationError):
        dplans.create_consent(
            owner_db,
            tenant_id=tid,
            plan_id=plan.id,
            procedure_record_id=plan.id,
            consenter_name="Pat",
        )
    with pytest.raises(ValidationError):
        dplans.create_consent(owner_db, tenant_id=tid, consenter_name="Pat")
    c = dplans.create_consent(
        owner_db,
        tenant_id=tid,
        plan_id=plan.id,
        consenter_name="Pat Clinical",
        consenter_relation="self",
    )
    assert c.status == DM.CONSENT_PENDING
    granted = dplans.decide_consent(
        owner_db,
        tenant_id=tid,
        consent_id=c.id,
        decision="granted",
        actor_id=b["admin"].id,
    )
    assert granted.status == DM.CONSENT_GRANTED
    with pytest.raises(ConflictError):
        dplans.decide_consent(
            owner_db,
            tenant_id=tid,
            consent_id=c.id,
            decision="declined",
            actor_id=b["admin"].id,
        )
    withdrawn = dplans.withdraw_consent(
        owner_db, tenant_id=tid, consent_id=c.id, actor_id=b["admin"].id
    )
    assert withdrawn.status == DM.CONSENT_WITHDRAWN


def test_recall_lifecycle(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    tid = b["tenant"].id
    r = dplans.create_recall(
        owner_db,
        tenant_id=tid,
        actor_id=b["admin"].id,
        patient_id=b["patient"].id,
        practitioner_id=b["practitioner"].id,
        location_id=b["location"].id,
        due_date=date(2027, 5, 1),
        reason="six-month review",
    )
    assert r.status == DM.RECALL_SCHEDULED
    done = dplans.transition_recall(
        owner_db, tenant_id=tid, recall_id=r.id, to_status="completed"
    )
    assert done.status == DM.RECALL_COMPLETED
    with pytest.raises(ConflictError):
        dplans.transition_recall(
            owner_db, tenant_id=tid, recall_id=r.id, to_status="missed"
        )


def test_document_ref_validation(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    e = _open(owner_db, b)
    tid = b["tenant"].id
    ref = dplans.create_document_ref(
        owner_db,
        tenant_id=tid,
        encounter_id=e.id,
        actor_id=b["admin"].id,
        doc_type="xray",
        storage_key="tenant/x/16-periapical.png",
        sha256="abc",
    )
    assert ref.doc_type == "xray"
    with pytest.raises(ValidationError):
        dplans.create_document_ref(
            owner_db,
            tenant_id=tid,
            encounter_id=e.id,
            actor_id=b["admin"].id,
            doc_type="mri",
            storage_key="k",
        )
    with pytest.raises(ValidationError):
        dplans.create_document_ref(
            owner_db,
            tenant_id=tid,
            encounter_id=e.id,
            actor_id=b["admin"].id,
            doc_type="xray",
            storage_key="  ",
        )


def test_location_scope_denied_for_clinical(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    import uuid

    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    e = _open(owner_db, b)
    tid = b["tenant"].id
    scope = frozenset({uuid.uuid4()})
    with pytest.raises(ForbiddenError):
        rec.create_note(
            owner_db,
            tenant_id=tid,
            encounter_id=e.id,
            author_id=b["practitioner"].id,
            assessment="x",
            location_ids=scope,
        )
    with pytest.raises(ForbiddenError):
        rx.create_prescription(
            owner_db,
            tenant_id=tid,
            encounter_id=e.id,
            prescribed_by=b["practitioner"].id,
            items=_rx_items(),
            location_ids=scope,
        )
    with pytest.raises(ForbiddenError):
        dental.record_finding(
            owner_db,
            tenant_id=tid,
            encounter_id=e.id,
            practitioner_id=b["practitioner"].id,
            tooth=16,
            condition_code="caries",
            location_ids=scope,
        )


def test_correct_prescription_requires_verified_prescriber(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    """Regression: correct path must verify the prescriber like create does."""
    from app.modules.tenancy import service as tenancy_service

    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    e = _open(owner_db, b)
    tid = b["tenant"].id
    p = rx.create_prescription(
        owner_db,
        tenant_id=tid,
        encounter_id=e.id,
        prescribed_by=b["practitioner"].id,
        items=_rx_items(),
    )
    rx.sign_prescription(
        owner_db, tenant_id=tid, prescription_id=p.id, actor_id=b["practitioner"].id
    )
    rogue = tenancy_service.register_practitioner(owner_db, display_name="Rogue Rx")
    owner_db.commit()
    with pytest.raises((ForbiddenError, NotFoundError)):
        rx.correct_prescription(
            owner_db,
            tenant_id=tid,
            prescription_id=p.id,
            prescribed_by=rogue.id,
            items=_rx_items(frequency="BID"),
        )


def test_get_prescription_enforces_location_scope(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    """Regression: direct prescription GET must honor encounter location."""
    import uuid

    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    e = _open(owner_db, b)
    tid = b["tenant"].id
    p = rx.create_prescription(
        owner_db,
        tenant_id=tid,
        encounter_id=e.id,
        prescribed_by=b["practitioner"].id,
        items=_rx_items(),
    )
    got = rx.get_prescription(owner_db, tenant_id=tid, prescription_id=p.id)
    assert got.id == p.id
    with pytest.raises(ForbiddenError):
        rx.get_prescription(
            owner_db,
            tenant_id=tid,
            prescription_id=p.id,
            location_ids=frozenset({uuid.uuid4()}),
        )


def test_plan_read_paths_enforce_location_scope(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    """Regression: plan get/list must honor the linked encounter location."""
    import uuid

    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    e = _open(owner_db, b)
    tid = b["tenant"].id
    plan = dplans.create_plan(
        owner_db,
        tenant_id=tid,
        actor_id=b["admin"].id,
        patient_id=b["patient"].id,
        practitioner_id=b["practitioner"].id,
        encounter_id=e.id,
    )
    scope = frozenset({uuid.uuid4()})
    with pytest.raises(ForbiddenError):
        dplans.get_plan(owner_db, tenant_id=tid, plan_id=plan.id, location_ids=scope)
    assert (
        dplans.list_plans(
            owner_db,
            tenant_id=tid,
            patient_id=b["patient"].id,
            location_ids=scope,
        )
        == []
    )
    assert dplans.get_plan(owner_db, tenant_id=tid, plan_id=plan.id).id == plan.id
