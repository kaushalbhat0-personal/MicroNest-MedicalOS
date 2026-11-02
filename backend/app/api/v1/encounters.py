"""Encounter + generic clinical endpoints. Thin adapters: tenant match +
permission gate, then service calls. Audit entries carry opaque IDs only —
clinical content never enters audit, logs, or outbox payloads."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DBSession

from app.api.deps import get_db, require
from app.api.v1._shared import match_tenant, practitioner_for_user
from app.modules.audit import service as audit_service
from app.modules.clinical import records as rec
from app.modules.clinical import schemas as S
from app.modules.clinical import service as encounters
from app.modules.clinical.models import ClinicalNote, Encounter, EncounterDiagnosis, Observation
from app.platform.authz.permissions import P
from app.platform.authz.scope import RequestContext
from app.platform.request_context import request_id_ctx

router = APIRouter(tags=["clinical"])


def _audit(db: DBSession, ctx: RequestContext, *, action: str, rtype: str, rid: str) -> None:
    audit_service.append(
        db,
        tenant_id=ctx.tenant_id,
        actor_type="user",
        actor_id=str(ctx.user_id),
        action=action,
        resource_type=rtype,
        resource_id=rid,
        request_id=request_id_ctx.get(),
    )


def _encounter_resp(e: Encounter) -> S.EncounterResponse:
    return S.EncounterResponse(
        id=e.id,
        tenant_id=e.tenant_id,
        patient_id=e.patient_id,
        practitioner_id=e.practitioner_id,
        location_id=e.location_id,
        appointment_id=e.appointment_id,
        chief_complaint=e.chief_complaint,
        status=e.status,
        version=e.version,
        opened_by=e.opened_by,
        opened_at=e.opened_at,
        closed_by=e.closed_by,
        closed_at=e.closed_at,
        close_reason=e.close_reason,
        created_at=e.created_at,
        updated_at=e.updated_at,
    )


def _note_resp(n: ClinicalNote) -> S.NoteResponse:
    return S.NoteResponse(
        id=n.id,
        tenant_id=n.tenant_id,
        encounter_id=n.encounter_id,
        author_id=n.author_id,
        note_type=n.note_type,
        chief_complaint=n.chief_complaint,
        subjective=n.subjective,
        objective=n.objective,
        assessment=n.assessment,
        plan=n.plan,
        status=n.status,
        version=n.version,
        is_addendum=n.is_addendum,
        supersedes_id=n.supersedes_id,
        superseded_by_id=n.superseded_by_id,
        created_at=n.created_at,
        updated_at=n.updated_at,
    )


def _obs_resp(db: DBSession, o: Observation) -> S.ObservationResponse:
    from app.modules.clinical.models import ObservationType

    otype = db.get(ObservationType, o.type_id)
    code = otype.code if otype else ""
    display = otype.display if otype else ""
    return S.ObservationResponse(
        id=o.id,
        tenant_id=o.tenant_id,
        encounter_id=o.encounter_id,
        type_code=code,
        type_display=display,
        value_numeric=float(o.value_numeric),
        value_text=o.value_text,
        unit=o.unit,
        taken_at=o.taken_at,
        corrects_id=o.corrects_id,
        corrected_by_id=o.corrected_by_id,
        created_at=o.created_at,
    )


def _dx_resp(db: DBSession, d: EncounterDiagnosis) -> S.DiagnosisResponse:
    code = display = None
    if d.diagnosis_id is not None:
        from app.modules.clinical.models import DiagnosisCode

        row = db.get(DiagnosisCode, d.diagnosis_id)
        if row is not None:
            code, display = row.code, row.display
    return S.DiagnosisResponse(
        id=d.id,
        tenant_id=d.tenant_id,
        encounter_id=d.encounter_id,
        diagnosis_code=code,
        diagnosis_display=display,
        free_text=d.free_text,
        is_primary=d.is_primary,
        status=d.status,
        review_needed=d.review_needed,
        onset_date=d.onset_date,
        supersedes_id=d.supersedes_id,
        superseded_by_id=d.superseded_by_id,
        created_at=d.created_at,
        updated_at=d.updated_at,
    )


@router.post("/tenants/{tenant_id}/encounters", response_model=S.EncounterResponse)
def open_encounter(
    tenant_id: uuid.UUID,
    body: S.EncounterOpenRequest,
    ctx: RequestContext = Depends(require(P.ENCOUNTER_OPEN)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.EncounterResponse:
    match_tenant(ctx, tenant_id)
    enc = encounters.open_encounter(
        db,
        tenant_id=tenant_id,
        actor_id=ctx.user_id,
        patient_id=body.patient_id,
        practitioner_id=body.practitioner_id,
        location_id=body.location_id,
        appointment_id=body.appointment_id,
        chief_complaint=body.chief_complaint,
        location_ids=ctx.location_ids,
    )
    _audit(db, ctx, action="encounter.opened", rtype="encounter", rid=str(enc.id))
    return _encounter_resp(enc)


@router.get("/tenants/{tenant_id}/encounters", response_model=S.EncounterListResponse)
def list_encounters(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.ENCOUNTER_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    patient_id: uuid.UUID | None = None,
    practitioner_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    status: str | None = None,
    limit: int = 50,
    cursor: uuid.UUID | None = None,
) -> S.EncounterListResponse:
    match_tenant(ctx, tenant_id)
    items, next_cursor = encounters.list_encounters(
        db,
        tenant_id=tenant_id,
        location_ids=ctx.location_ids,
        patient_id=patient_id,
        practitioner_id=practitioner_id,
        location_id=location_id,
        status=status,
        limit=limit,
        cursor=cursor,
    )
    return S.EncounterListResponse(
        items=[_encounter_resp(e) for e in items], next_cursor=next_cursor
    )


@router.get("/tenants/{tenant_id}/encounters/{encounter_id}", response_model=S.EncounterResponse)
def get_encounter(
    tenant_id: uuid.UUID,
    encounter_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.ENCOUNTER_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.EncounterResponse:
    match_tenant(ctx, tenant_id)
    enc = encounters.get_encounter(db, tenant_id=tenant_id, encounter_id=encounter_id)
    if ctx.location_ids and enc.location_id not in ctx.location_ids:
        from app.platform.errors import ForbiddenError

        raise ForbiddenError("location is outside your scope")
    return _encounter_resp(enc)


@router.post(
    "/tenants/{tenant_id}/encounters/{encounter_id}/close",
    response_model=S.EncounterResponse,
)
def close_encounter(
    tenant_id: uuid.UUID,
    encounter_id: uuid.UUID,
    body: S.EncounterCloseRequest,
    ctx: RequestContext = Depends(require(P.ENCOUNTER_CLOSE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.EncounterResponse:
    match_tenant(ctx, tenant_id)
    enc = encounters.close_encounter(
        db,
        tenant_id=tenant_id,
        encounter_id=encounter_id,
        actor_id=ctx.user_id,
        note_waiver=body.note_waiver,
        vitals_waiver=body.vitals_waiver,
        reason=body.reason,
        location_ids=ctx.location_ids,
    )
    _audit(db, ctx, action="encounter.closed", rtype="encounter", rid=str(enc.id))
    return _encounter_resp(enc)


@router.post(
    "/tenants/{tenant_id}/encounters/{encounter_id}/clinical-notes",
    response_model=S.NoteResponse,
)
def create_note(
    tenant_id: uuid.UUID,
    encounter_id: uuid.UUID,
    body: S.NoteCreateRequest,
    ctx: RequestContext = Depends(require(P.CLINICAL_CREATE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.NoteResponse:
    match_tenant(ctx, tenant_id)
    author = practitioner_for_user(db, ctx.user_id)
    note = rec.create_note(
        db,
        tenant_id=tenant_id,
        encounter_id=encounter_id,
        author_id=author.id,
        note_type=body.note_type,
        chief_complaint=body.chief_complaint,
        subjective=body.subjective,
        objective=body.objective,
        assessment=body.assessment,
        plan=body.plan,
        location_ids=ctx.location_ids,
    )
    _audit(db, ctx, action="note.created", rtype="clinical_note", rid=str(note.id))
    return _note_resp(note)


@router.get(
    "/tenants/{tenant_id}/encounters/{encounter_id}/clinical-notes",
    response_model=list[S.NoteResponse],
)
def list_notes(
    tenant_id: uuid.UUID,
    encounter_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.CLINICAL_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> list[S.NoteResponse]:
    match_tenant(ctx, tenant_id)
    return [
        _note_resp(n)
        for n in rec.list_notes(
            db, tenant_id=tenant_id, encounter_id=encounter_id, location_ids=ctx.location_ids
        )
    ]


@router.post(
    "/tenants/{tenant_id}/clinical-notes/{note_id}/finalize", response_model=S.NoteResponse
)
def finalize_note(
    tenant_id: uuid.UUID,
    note_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.CLINICAL_CREATE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.NoteResponse:
    match_tenant(ctx, tenant_id)
    author = practitioner_for_user(db, ctx.user_id)
    note = rec.finalize_note(
        db,
        tenant_id=tenant_id,
        note_id=note_id,
        actor_id=author.id,
        location_ids=ctx.location_ids,
    )
    _audit(db, ctx, action="note.finalized", rtype="clinical_note", rid=str(note.id))
    return _note_resp(note)


@router.post("/tenants/{tenant_id}/clinical-notes/{note_id}/amend", response_model=S.NoteResponse)
def amend_note(
    tenant_id: uuid.UUID,
    note_id: uuid.UUID,
    body: S.NoteCreateRequest,
    ctx: RequestContext = Depends(require(P.CLINICAL_CREATE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.NoteResponse:
    match_tenant(ctx, tenant_id)
    author = practitioner_for_user(db, ctx.user_id)
    note = rec.amend_note(
        db,
        tenant_id=tenant_id,
        note_id=note_id,
        actor_id=author.id,
        location_ids=ctx.location_ids,
        chief_complaint=body.chief_complaint,
        subjective=body.subjective,
        objective=body.objective,
        assessment=body.assessment,
        plan=body.plan,
    )
    _audit(db, ctx, action="note.amended", rtype="clinical_note", rid=str(note.id))
    return _note_resp(note)


@router.post(
    "/tenants/{tenant_id}/encounters/{encounter_id}/observations",
    response_model=S.ObservationResponse,
)
def record_observation(
    tenant_id: uuid.UUID,
    encounter_id: uuid.UUID,
    body: S.ObservationCreateRequest,
    ctx: RequestContext = Depends(require(P.CLINICAL_CREATE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.ObservationResponse:
    match_tenant(ctx, tenant_id)
    obs = rec.record_observation(
        db,
        tenant_id=tenant_id,
        encounter_id=encounter_id,
        type_code=body.type_code,
        value_numeric=body.value_numeric,
        value_text=body.value_text,
        taken_at=body.taken_at,
        recorded_by=ctx.user_id,
        location_ids=ctx.location_ids,
    )
    _audit(db, ctx, action="observation.recorded", rtype="observation", rid=str(obs.id))
    return _obs_resp(db, obs)


@router.get(
    "/tenants/{tenant_id}/encounters/{encounter_id}/observations",
    response_model=list[S.ObservationResponse],
)
def list_observations(
    tenant_id: uuid.UUID,
    encounter_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.CLINICAL_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> list[S.ObservationResponse]:
    match_tenant(ctx, tenant_id)
    return [
        _obs_resp(db, o)
        for o in rec.list_observations(
            db, tenant_id=tenant_id, encounter_id=encounter_id, location_ids=ctx.location_ids
        )
    ]


@router.post(
    "/tenants/{tenant_id}/observations/{observation_id}/amend",
    response_model=S.ObservationResponse,
)
def amend_observation(
    tenant_id: uuid.UUID,
    observation_id: uuid.UUID,
    body: S.ObservationCreateRequest,
    ctx: RequestContext = Depends(require(P.CLINICAL_CREATE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.ObservationResponse:
    match_tenant(ctx, tenant_id)
    obs = rec.amend_observation(
        db,
        tenant_id=tenant_id,
        observation_id=observation_id,
        value_numeric=body.value_numeric,
        value_text=body.value_text,
        recorded_by=ctx.user_id,
        location_ids=ctx.location_ids,
    )
    _audit(db, ctx, action="observation.amended", rtype="observation", rid=str(obs.id))
    return _obs_resp(db, obs)


@router.get(
    "/tenants/{tenant_id}/observation-types", response_model=list[S.ObservationTypeResponse]
)
def list_observation_types(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.CLINICAL_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> list[S.ObservationTypeResponse]:
    match_tenant(ctx, tenant_id)
    return [
        S.ObservationTypeResponse(
            id=t.id,
            code=t.code,
            display=t.display,
            unit=t.unit,
            min_value=float(t.min_value) if t.min_value is not None else None,
            max_value=float(t.max_value) if t.max_value is not None else None,
            is_active=t.is_active,
        )
        for t in rec.list_observation_types(db)
    ]


@router.post(
    "/tenants/{tenant_id}/encounters/{encounter_id}/diagnoses",
    response_model=S.DiagnosisResponse,
)
def add_diagnosis(
    tenant_id: uuid.UUID,
    encounter_id: uuid.UUID,
    body: S.DiagnosisCreateRequest,
    ctx: RequestContext = Depends(require(P.CLINICAL_CREATE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.DiagnosisResponse:
    match_tenant(ctx, tenant_id)
    dx = rec.add_diagnosis(
        db,
        tenant_id=tenant_id,
        encounter_id=encounter_id,
        diagnosis_code=body.diagnosis_code,
        free_text=body.free_text,
        is_primary=body.is_primary,
        onset_date=body.onset_date,
        recorded_by=ctx.user_id,
        location_ids=ctx.location_ids,
    )
    _audit(db, ctx, action="diagnosis.added", rtype="diagnosis", rid=str(dx.id))
    return _dx_resp(db, dx)


@router.get(
    "/tenants/{tenant_id}/encounters/{encounter_id}/diagnoses",
    response_model=list[S.DiagnosisResponse],
)
def list_diagnoses(
    tenant_id: uuid.UUID,
    encounter_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.CLINICAL_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> list[S.DiagnosisResponse]:
    match_tenant(ctx, tenant_id)
    return [
        _dx_resp(db, d)
        for d in rec.list_diagnoses(
            db, tenant_id=tenant_id, encounter_id=encounter_id, location_ids=ctx.location_ids
        )
    ]


@router.post(
    "/tenants/{tenant_id}/diagnoses/{diagnosis_id}/resolve",
    response_model=S.DiagnosisResponse,
)
def resolve_diagnosis(
    tenant_id: uuid.UUID,
    diagnosis_id: uuid.UUID,
    body: S.DiagnosisResolveRequest,
    ctx: RequestContext = Depends(require(P.CLINICAL_CREATE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.DiagnosisResponse:
    match_tenant(ctx, tenant_id)
    dx = rec.resolve_diagnosis(
        db,
        tenant_id=tenant_id,
        diagnosis_id=diagnosis_id,
        outcome=body.outcome,
        location_ids=ctx.location_ids,
    )
    _audit(db, ctx, action="diagnosis.resolved", rtype="diagnosis", rid=str(dx.id))
    return _dx_resp(db, dx)


@router.post(
    "/tenants/{tenant_id}/diagnoses/{diagnosis_id}/supersede",
    response_model=S.DiagnosisResponse,
)
def supersede_diagnosis(
    tenant_id: uuid.UUID,
    diagnosis_id: uuid.UUID,
    body: S.DiagnosisCreateRequest,
    ctx: RequestContext = Depends(require(P.CLINICAL_CREATE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.DiagnosisResponse:
    match_tenant(ctx, tenant_id)
    dx = rec.supersede_diagnosis(
        db,
        tenant_id=tenant_id,
        diagnosis_id=diagnosis_id,
        recorded_by=ctx.user_id,
        location_ids=ctx.location_ids,
        diagnosis_code=body.diagnosis_code,
        free_text=body.free_text,
        is_primary=body.is_primary,
    )
    _audit(db, ctx, action="diagnosis.superseded", rtype="diagnosis", rid=str(dx.id))
    return _dx_resp(db, dx)


@router.get("/tenants/{tenant_id}/diagnosis-codes", response_model=list[S.DiagnosisCodeResponse])
def list_diagnosis_codes(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.CLINICAL_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> list[S.DiagnosisCodeResponse]:
    match_tenant(ctx, tenant_id)
    return [
        S.DiagnosisCodeResponse(
            id=r.id,
            code=r.code,
            display=r.display,
            icd10=r.icd10,
            snomed=r.snomed,
            needs_review=r.needs_review,
            is_active=r.is_active,
        )
        for r in rec.list_diagnosis_codes(db)
    ]
