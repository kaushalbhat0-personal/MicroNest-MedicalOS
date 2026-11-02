"""Clinical domain: encounter lifecycle + closure, notes, observations,
diagnoses, immutability and supersede chains. Service-level (owner session)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.modules.clinical import models as M
from app.modules.clinical import records as rec
from app.modules.clinical import service as enc
from app.platform.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)


def _open(db, b, **kw):  # type: ignore[no-untyped-def]
    args = {
        "tenant_id": b["tenant"].id,
        "actor_id": b["admin"].id,
        "patient_id": b["patient"].id,
        "practitioner_id": b["practitioner"].id,
        "location_id": b["location"].id,
    }
    args.update(kw)
    return enc.open_encounter(db, **args)  # type: ignore[arg-type]


def test_open_defaults_to_walk_in_without_appointment(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from tests.helpers import provision_clinical

    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    e = _open(owner_db, b)
    assert e.status == M.ENCOUNTER_OPEN
    assert e.appointment_id is None
    assert e.version == 1


def test_open_with_appointment_links_and_validates_patient(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from app.modules.scheduling import service as sched
    from tests.helpers import provision_clinical

    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    appt = sched.create_appointment(
        owner_db,
        tenant_id=b["tenant"].id,
        actor_id=b["admin"].id,
        patient_id=b["patient"].id,
        practitioner_id=b["practitioner"].id,
        location_id=b["location"].id,
        start=datetime.now(timezone.utc) + timedelta(days=1),
        duration_minutes=30,
    )
    e = _open(owner_db, b, appointment_id=appt.id)
    assert e.appointment_id == appt.id


def test_open_requires_verified_practitioner(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from app.modules.tenancy import service as tenancy_service
    from tests.helpers import provision_clinical

    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    rogue = tenancy_service.register_practitioner(owner_db, display_name="Rogue")
    owner_db.commit()
    with pytest.raises((ForbiddenError, NotFoundError)):
        _open(owner_db, b, practitioner_id=rogue.id)


def test_close_requires_note_or_waiver(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    from tests.helpers import provision_clinical

    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    e = _open(owner_db, b)
    rec.record_observation(
        owner_db,
        tenant_id=b["tenant"].id,
        encounter_id=e.id,
        type_code="pulse",
        value_numeric=72,
    )
    with pytest.raises(ValidationError):
        enc.close_encounter(
            owner_db,
            tenant_id=b["tenant"].id,
            encounter_id=e.id,
            actor_id=b["admin"].id,
        )
    closed = enc.close_encounter(
        owner_db,
        tenant_id=b["tenant"].id,
        encounter_id=e.id,
        actor_id=b["admin"].id,
        note_waiver=True,
    )
    assert closed.status == M.ENCOUNTER_CLOSED
    assert closed.closed_by == b["admin"].id


def test_close_requires_vitals_or_waiver_and_finalized_note(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from tests.helpers import provision_clinical

    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    e = _open(owner_db, b)
    note = rec.create_note(
        owner_db,
        tenant_id=b["tenant"].id,
        encounter_id=e.id,
        author_id=b["practitioner"].id,
        assessment=" viral URI",
    )
    with pytest.raises(ValidationError):
        enc.close_encounter(
            owner_db,
            tenant_id=b["tenant"].id,
            encounter_id=e.id,
            actor_id=b["admin"].id,
        )
    rec.finalize_note(
        owner_db,
        tenant_id=b["tenant"].id,
        note_id=note.id,
        actor_id=b["practitioner"].id,
    )
    with pytest.raises(ValidationError):
        enc.close_encounter(
            owner_db,
            tenant_id=b["tenant"].id,
            encounter_id=e.id,
            actor_id=b["admin"].id,
        )
    closed = enc.close_encounter(
        owner_db,
        tenant_id=b["tenant"].id,
        encounter_id=e.id,
        actor_id=b["admin"].id,
        vitals_waiver=True,
    )
    assert closed.status == M.ENCOUNTER_CLOSED


def test_close_blocked_by_draft_prescription(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from app.modules.prescriptions import service as rx
    from tests.helpers import provision_clinical

    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    e = _open(owner_db, b)
    note = rec.create_note(
        owner_db,
        tenant_id=b["tenant"].id,
        encounter_id=e.id,
        author_id=b["practitioner"].id,
        assessment="needs meds",
    )
    rec.finalize_note(
        owner_db,
        tenant_id=b["tenant"].id,
        note_id=note.id,
        actor_id=b["practitioner"].id,
    )
    rec.record_observation(
        owner_db,
        tenant_id=b["tenant"].id,
        encounter_id=e.id,
        type_code="pulse",
        value_numeric=80,
    )
    rx.create_prescription(
        owner_db,
        tenant_id=b["tenant"].id,
        encounter_id=e.id,
        prescribed_by=b["practitioner"].id,
        items=[
            {
                "medication_code": "paracetamol-650",
                "dose": "650 mg",
                "route": "oral",
                "frequency": "TID",
                "instructions": "after food",
            }
        ],
    )
    with pytest.raises(ConflictError):
        enc.close_encounter(
            owner_db,
            tenant_id=b["tenant"].id,
            encounter_id=e.id,
            actor_id=b["admin"].id,
        )


def test_closed_encounter_is_terminal(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    from tests.helpers import provision_clinical

    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    e = _open(owner_db, b)
    enc.close_encounter(
        owner_db,
        tenant_id=b["tenant"].id,
        encounter_id=e.id,
        actor_id=b["admin"].id,
        note_waiver=True,
        vitals_waiver=True,
    )
    with pytest.raises(ConflictError):
        enc.close_encounter(
            owner_db,
            tenant_id=b["tenant"].id,
            encounter_id=e.id,
            actor_id=b["admin"].id,
            note_waiver=True,
            vitals_waiver=True,
        )


def test_note_finalize_requires_author(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    from app.modules.tenancy import service as tenancy_service
    from tests.helpers import provision_clinical

    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    e = _open(owner_db, b)
    other = tenancy_service.register_practitioner(owner_db, display_name="Other")
    tenancy_service.set_verification(
        owner_db, tenant=b["tenant"], practitioner=other, status="approved"
    )
    note = rec.create_note(
        owner_db,
        tenant_id=b["tenant"].id,
        encounter_id=e.id,
        author_id=b["practitioner"].id,
        assessment="a",
    )
    with pytest.raises(ForbiddenError):
        rec.finalize_note(
            owner_db, tenant_id=b["tenant"].id, note_id=note.id, actor_id=other.id
        )


def test_note_amend_creates_superseding_finalized_copy(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from tests.helpers import provision_clinical

    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    e = _open(owner_db, b)
    tid = b["tenant"].id
    note = rec.create_note(
        owner_db,
        tenant_id=tid,
        encounter_id=e.id,
        author_id=b["practitioner"].id,
        assessment="initial",
    )
    rec.finalize_note(
        owner_db, tenant_id=tid, note_id=note.id, actor_id=b["practitioner"].id
    )
    fixed = rec.amend_note(
        owner_db,
        tenant_id=tid,
        note_id=note.id,
        actor_id=b["practitioner"].id,
        assessment="corrected",
    )
    assert fixed.status == M.NOTE_FINALIZED
    assert fixed.supersedes_id == note.id
    assert fixed.version == note.version + 1
    old = rec.get_note(owner_db, tenant_id=tid, note_id=note.id)
    assert old.status == M.NOTE_AMENDED
    assert old.superseded_by_id == fixed.id
    assert old.assessment == "initial"  # original content untouched
    with pytest.raises(ConflictError):
        rec.amend_note(
            owner_db,
            tenant_id=tid,
            note_id=note.id,
            actor_id=b["practitioner"].id,
            assessment="again",
        )


def test_observation_range_validation(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    from tests.helpers import provision_clinical

    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    e = _open(owner_db, b)
    tid = b["tenant"].id
    obs = rec.record_observation(
        owner_db,
        tenant_id=tid,
        encounter_id=e.id,
        type_code="bp_systolic",
        value_numeric=120,
    )
    assert obs.unit == "mmHg"
    with pytest.raises(ValidationError):
        rec.record_observation(
            owner_db,
            tenant_id=tid,
            encounter_id=e.id,
            type_code="bp_systolic",
            value_numeric=400,
        )
    with pytest.raises(ValidationError):
        rec.record_observation(
            owner_db,
            tenant_id=tid,
            encounter_id=e.id,
            type_code="nope",
            value_numeric=1,
        )


def test_observation_amend_links_chain(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    from tests.helpers import provision_clinical

    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    e = _open(owner_db, b)
    tid = b["tenant"].id
    obs = rec.record_observation(
        owner_db, tenant_id=tid, encounter_id=e.id, type_code="pulse", value_numeric=72
    )
    fixed = rec.amend_observation(
        owner_db, tenant_id=tid, observation_id=obs.id, value_numeric=76
    )
    assert fixed.corrects_id == obs.id
    assert (
        rec.get_observation(
            owner_db, tenant_id=tid, observation_id=obs.id
        ).corrected_by_id
        == fixed.id
    )
    with pytest.raises(ConflictError):
        rec.amend_observation(
            owner_db, tenant_id=tid, observation_id=obs.id, value_numeric=80
        )


def test_diagnosis_coded_and_free_text_and_supersede(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    from tests.helpers import provision_clinical

    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    e = _open(owner_db, b)
    tid = b["tenant"].id
    coded = rec.add_diagnosis(
        owner_db,
        tenant_id=tid,
        encounter_id=e.id,
        diagnosis_code="K02.9",
        is_primary=True,
    )
    assert coded.review_needed is False
    assert coded.status == M.DX_ACTIVE
    free = rec.add_diagnosis(
        owner_db, tenant_id=tid, encounter_id=e.id, free_text="watch this molar"
    )
    assert free.review_needed is True
    assert free.diagnosis_id is None
    with pytest.raises(ValidationError):
        rec.add_diagnosis(
            owner_db,
            tenant_id=tid,
            encounter_id=e.id,
            diagnosis_code="K02.9",
            free_text="both",
        )
    with pytest.raises(ValidationError):
        rec.add_diagnosis(owner_db, tenant_id=tid, encounter_id=e.id)
    resolved = rec.resolve_diagnosis(
        owner_db, tenant_id=tid, diagnosis_id=coded.id, outcome="resolved"
    )
    assert resolved.status == M.DX_RESOLVED
    with pytest.raises(ConflictError):
        rec.resolve_diagnosis(
            owner_db, tenant_id=tid, diagnosis_id=coded.id, outcome="resolved"
        )
    new = rec.supersede_diagnosis(
        owner_db,
        tenant_id=tid,
        diagnosis_id=free.id,
        free_text="watch this molar closely",
    )
    assert new.status == M.DX_ACTIVE
    assert new.supersedes_id == free.id
    old = rec.get_diagnosis(owner_db, tenant_id=tid, diagnosis_id=free.id)
    assert old.status == M.DX_SUPERSEDED


def test_amend_note_requires_verified_practitioner(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    """Regression: amend path must verify authorship like create does."""
    from app.modules.tenancy import service as tenancy_service
    from tests.helpers import provision_clinical

    b = provision_clinical(owner_db, make_owner_user, make_tenant)
    e = _open(owner_db, b)
    tid = b["tenant"].id
    note = rec.create_note(
        owner_db,
        tenant_id=tid,
        encounter_id=e.id,
        author_id=b["practitioner"].id,
        assessment="initial",
    )
    rec.finalize_note(
        owner_db, tenant_id=tid, note_id=note.id, actor_id=b["practitioner"].id
    )
    rogue = tenancy_service.register_practitioner(owner_db, display_name="Rogue Amend")
    owner_db.commit()
    with pytest.raises((ForbiddenError, NotFoundError)):
        rec.amend_note(
            owner_db,
            tenant_id=tid,
            note_id=note.id,
            actor_id=rogue.id,
            assessment="rogue edit",
        )
    assert (
        rec.get_note(owner_db, tenant_id=tid, note_id=note.id).status
        == M.NOTE_FINALIZED
    )
