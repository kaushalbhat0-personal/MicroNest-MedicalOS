"""Dental endpoints. Findings, plans, procedure records, consents, recalls,
and document references. Money fields do not exist at this layer; storage
bytes never pass through here (references only). Audit carries opaque IDs."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DBSession

from app.api.deps import get_db, require
from app.api.v1._shared import match_tenant, practitioner_for_user
from app.modules.audit import service as audit_service
from app.modules.dental import plans as dplans
from app.modules.dental import schemas as S
from app.modules.dental import service as dental
from app.modules.dental.models import (
    Consent,
    DentalProcedureRecord,
    DocumentReference,
    Recall,
    ToothFinding,
    TreatmentPlan,
    TreatmentPlanItem,
)
from app.platform.authz.permissions import P
from app.platform.authz.scope import RequestContext
from app.platform.request_context import request_id_ctx

router = APIRouter(tags=["dental"])


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


def _finding_resp(db: DBSession, f: ToothFinding) -> S.FindingResponse:
    from app.modules.dental.models import DentalCondition

    cond = db.get(DentalCondition, f.condition_id)
    assert cond is not None
    return S.FindingResponse(
        id=f.id,
        tenant_id=f.tenant_id,
        encounter_id=f.encounter_id,
        practitioner_id=f.practitioner_id,
        tooth=f.tooth,
        condition_code=cond.code,
        condition_display=cond.display,
        surfaces=dental.finding_surfaces(db, finding_id=f.id),
        status=f.status,
        details=f.details,
        created_at=f.created_at,
        updated_at=f.updated_at,
    )


@router.get(
    "/tenants/{tenant_id}/dental-conditions", response_model=list[S.DentalConditionResponse]
)
def list_conditions(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.DENTAL_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> list[S.DentalConditionResponse]:
    match_tenant(ctx, tenant_id)
    return [
        S.DentalConditionResponse(id=c.id, code=c.code, display=c.display, is_active=c.is_active)
        for c in dental.list_conditions(db)
    ]


@router.post(
    "/tenants/{tenant_id}/encounters/{encounter_id}/tooth-findings",
    response_model=S.FindingResponse,
)
def record_finding(
    tenant_id: uuid.UUID,
    encounter_id: uuid.UUID,
    body: S.FindingCreateRequest,
    ctx: RequestContext = Depends(require(P.DENTAL_RECORD)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.FindingResponse:
    match_tenant(ctx, tenant_id)
    author = practitioner_for_user(db, ctx.user_id)
    f = dental.record_finding(
        db,
        tenant_id=tenant_id,
        encounter_id=encounter_id,
        practitioner_id=author.id,
        tooth=body.tooth,
        condition_code=body.condition_code,
        surfaces=body.surfaces,
        details=body.details,
        recorded_by=ctx.user_id,
        location_ids=ctx.location_ids,
    )
    _audit(db, ctx, action="finding.recorded", rtype="tooth_finding", rid=str(f.id))
    return _finding_resp(db, f)


@router.get(
    "/tenants/{tenant_id}/encounters/{encounter_id}/tooth-findings",
    response_model=list[S.FindingResponse],
)
def list_findings(
    tenant_id: uuid.UUID,
    encounter_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.DENTAL_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> list[S.FindingResponse]:
    match_tenant(ctx, tenant_id)
    return [
        _finding_resp(db, f)
        for f in dental.list_findings(
            db, tenant_id=tenant_id, encounter_id=encounter_id, location_ids=ctx.location_ids
        )
    ]


@router.post(
    "/tenants/{tenant_id}/tooth-findings/{finding_id}/resolve",
    response_model=S.FindingResponse,
)
def resolve_finding(
    tenant_id: uuid.UUID,
    finding_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.DENTAL_RECORD)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.FindingResponse:
    match_tenant(ctx, tenant_id)
    f = dental.resolve_finding(
        db, tenant_id=tenant_id, finding_id=finding_id, location_ids=ctx.location_ids
    )
    _audit(db, ctx, action="finding.resolved", rtype="tooth_finding", rid=str(f.id))
    return _finding_resp(db, f)


@router.get(
    "/tenants/{tenant_id}/dental-procedures", response_model=list[S.DentalProcedureResponse]
)
def list_procedures(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.DENTAL_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> list[S.DentalProcedureResponse]:
    match_tenant(ctx, tenant_id)
    return [
        S.DentalProcedureResponse(
            id=p.id,
            code=p.code,
            display=p.display,
            description=p.description,
            specialty=p.specialty,
            external_code=p.external_code,
            is_active=p.is_active,
        )
        for p in dental.list_procedures(db)
    ]


def _plan_resp(db: DBSession, plan: TreatmentPlan) -> S.PlanResponse:
    items = []
    for i in dplans.plan_items(db, plan_id=plan.id):
        items.append(_plan_item_resp(db, i))
    return S.PlanResponse(
        id=plan.id,
        tenant_id=plan.tenant_id,
        patient_id=plan.patient_id,
        encounter_id=plan.encounter_id,
        practitioner_id=plan.practitioner_id,
        status=plan.status,
        version=plan.version,
        notes=plan.notes,
        items=items,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


def _plan_item_resp(db: DBSession, i: TreatmentPlanItem) -> S.PlanItemResponse:
    from app.modules.dental.models import DentalProcedure

    proc = db.get(DentalProcedure, i.procedure_id)
    assert proc is not None
    return S.PlanItemResponse(
        id=i.id,
        procedure_code=proc.code,
        procedure_display=proc.display,
        tooth=i.tooth,
        surface=i.surface,
        sequence=i.sequence,
        status=i.status,
        notes=i.notes,
    )


@router.post("/tenants/{tenant_id}/treatment-plans", response_model=S.PlanResponse)
def create_plan(
    tenant_id: uuid.UUID,
    body: S.PlanCreateRequest,
    ctx: RequestContext = Depends(require(P.PLAN_MANAGE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.PlanResponse:
    match_tenant(ctx, tenant_id)
    author = practitioner_for_user(db, ctx.user_id)
    plan = dplans.create_plan(
        db,
        tenant_id=tenant_id,
        actor_id=ctx.user_id,
        patient_id=body.patient_id,
        practitioner_id=author.id,
        encounter_id=body.encounter_id,
        notes=body.notes,
        location_ids=ctx.location_ids,
    )
    for item in body.items:
        dplans.add_plan_item(
            db,
            tenant_id=tenant_id,
            plan_id=plan.id,
            procedure_code=item.procedure_code,
            tooth=item.tooth,
            surface=item.surface,
            sequence=item.sequence,
            notes=item.notes,
            location_ids=ctx.location_ids,
        )
    _audit(db, ctx, action="plan.created", rtype="treatment_plan", rid=str(plan.id))
    return _plan_resp(db, plan)


@router.get("/tenants/{tenant_id}/treatment-plans", response_model=list[S.PlanResponse])
def list_plans(
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.DENTAL_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> list[S.PlanResponse]:
    match_tenant(ctx, tenant_id)
    return [
        _plan_resp(db, p)
        for p in dplans.list_plans(
            db,
            tenant_id=tenant_id,
            patient_id=patient_id,
            location_ids=ctx.location_ids,
        )
    ]


@router.get("/tenants/{tenant_id}/treatment-plans/{plan_id}", response_model=S.PlanResponse)
def get_plan(
    tenant_id: uuid.UUID,
    plan_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.DENTAL_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.PlanResponse:
    match_tenant(ctx, tenant_id)
    return _plan_resp(
        db,
        dplans.get_plan(db, tenant_id=tenant_id, plan_id=plan_id, location_ids=ctx.location_ids),
    )


@router.post(
    "/tenants/{tenant_id}/treatment-plans/{plan_id}/items",
    response_model=S.PlanItemResponse,
)
def add_plan_item(
    tenant_id: uuid.UUID,
    plan_id: uuid.UUID,
    body: S.PlanItemRequest,
    ctx: RequestContext = Depends(require(P.PLAN_MANAGE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.PlanItemResponse:
    match_tenant(ctx, tenant_id)
    item = dplans.add_plan_item(
        db,
        tenant_id=tenant_id,
        plan_id=plan_id,
        procedure_code=body.procedure_code,
        tooth=body.tooth,
        surface=body.surface,
        sequence=body.sequence,
        notes=body.notes,
        location_ids=ctx.location_ids,
    )
    _audit(db, ctx, action="plan.item_added", rtype="treatment_plan", rid=str(plan_id))
    return _plan_item_resp(db, item)


@router.post(
    "/tenants/{tenant_id}/treatment-plans/{plan_id}/activate", response_model=S.PlanResponse
)
def activate_plan(
    tenant_id: uuid.UUID,
    plan_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.PLAN_MANAGE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.PlanResponse:
    match_tenant(ctx, tenant_id)
    plan = dplans.activate_plan(
        db, tenant_id=tenant_id, plan_id=plan_id, location_ids=ctx.location_ids
    )
    _audit(db, ctx, action="plan.activated", rtype="treatment_plan", rid=str(plan.id))
    return _plan_resp(db, plan)


@router.post(
    "/tenants/{tenant_id}/treatment-plans/{plan_id}/complete", response_model=S.PlanResponse
)
def complete_plan(
    tenant_id: uuid.UUID,
    plan_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.PLAN_MANAGE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.PlanResponse:
    match_tenant(ctx, tenant_id)
    plan = dplans.complete_plan(
        db, tenant_id=tenant_id, plan_id=plan_id, location_ids=ctx.location_ids
    )
    _audit(db, ctx, action="plan.completed", rtype="treatment_plan", rid=str(plan.id))
    return _plan_resp(db, plan)


@router.post("/tenants/{tenant_id}/treatment-plans/{plan_id}/cancel", response_model=S.PlanResponse)
def cancel_plan(
    tenant_id: uuid.UUID,
    plan_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.PLAN_MANAGE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.PlanResponse:
    match_tenant(ctx, tenant_id)
    plan = dplans.cancel_plan(
        db, tenant_id=tenant_id, plan_id=plan_id, location_ids=ctx.location_ids
    )
    _audit(db, ctx, action="plan.cancelled", rtype="treatment_plan", rid=str(plan.id))
    return _plan_resp(db, plan)


@router.post(
    "/tenants/{tenant_id}/plan-items/{item_id}/status",
    response_model=S.PlanItemResponse,
)
def transition_plan_item(
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    body: S.PlanItemStatusRequest,
    ctx: RequestContext = Depends(require(P.PLAN_MANAGE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.PlanItemResponse:
    match_tenant(ctx, tenant_id)
    item = dplans.transition_plan_item(
        db,
        tenant_id=tenant_id,
        item_id=item_id,
        to_status=body.status,
        location_ids=ctx.location_ids,
    )
    _audit(db, ctx, action="plan.item_status", rtype="treatment_plan", rid=str(item.plan_id))
    return _plan_item_resp(db, item)


def _record_resp(db: DBSession, r: DentalProcedureRecord) -> S.ProcedureRecordResponse:
    from app.modules.dental.models import DentalProcedure

    proc = db.get(DentalProcedure, r.procedure_id)
    assert proc is not None
    return S.ProcedureRecordResponse(
        id=r.id,
        tenant_id=r.tenant_id,
        encounter_id=r.encounter_id,
        practitioner_id=r.practitioner_id,
        procedure_code=proc.code,
        procedure_display=proc.display,
        plan_item_id=r.plan_item_id,
        tooth=r.tooth,
        surface=r.surface,
        status=r.status,
        notes=r.notes,
        performed_at=r.performed_at,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


@router.post(
    "/tenants/{tenant_id}/encounters/{encounter_id}/procedure-records",
    response_model=S.ProcedureRecordResponse,
)
def record_procedure(
    tenant_id: uuid.UUID,
    encounter_id: uuid.UUID,
    body: S.ProcedureRecordCreateRequest,
    ctx: RequestContext = Depends(require(P.DENTAL_RECORD)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.ProcedureRecordResponse:
    match_tenant(ctx, tenant_id)
    author = practitioner_for_user(db, ctx.user_id)
    r = dplans.record_procedure(
        db,
        tenant_id=tenant_id,
        encounter_id=encounter_id,
        practitioner_id=author.id,
        procedure_code=body.procedure_code,
        plan_item_id=body.plan_item_id,
        tooth=body.tooth,
        surface=body.surface,
        notes=body.notes,
        location_ids=ctx.location_ids,
    )
    _audit(db, ctx, action="procedure.recorded", rtype="procedure_record", rid=str(r.id))
    return _record_resp(db, r)


@router.get(
    "/tenants/{tenant_id}/encounters/{encounter_id}/procedure-records",
    response_model=list[S.ProcedureRecordResponse],
)
def list_procedure_records(
    tenant_id: uuid.UUID,
    encounter_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.DENTAL_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> list[S.ProcedureRecordResponse]:
    match_tenant(ctx, tenant_id)
    return [
        _record_resp(db, r)
        for r in dplans.list_procedure_records(
            db, tenant_id=tenant_id, encounter_id=encounter_id, location_ids=ctx.location_ids
        )
    ]


@router.post(
    "/tenants/{tenant_id}/procedure-records/{record_id}/status",
    response_model=S.ProcedureRecordResponse,
)
def transition_procedure_record(
    tenant_id: uuid.UUID,
    record_id: uuid.UUID,
    body: S.ProcedureRecordStatusRequest,
    ctx: RequestContext = Depends(require(P.DENTAL_RECORD)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.ProcedureRecordResponse:
    match_tenant(ctx, tenant_id)
    r = dplans.transition_procedure_record(
        db,
        tenant_id=tenant_id,
        record_id=record_id,
        to_status=body.status,
        location_ids=ctx.location_ids,
    )
    _audit(db, ctx, action="procedure.status", rtype="procedure_record", rid=str(r.id))
    return _record_resp(db, r)


def _consent_resp(c: Consent) -> S.ConsentResponse:
    return S.ConsentResponse(
        id=c.id,
        tenant_id=c.tenant_id,
        plan_id=c.plan_id,
        procedure_record_id=c.procedure_record_id,
        status=c.status,
        consenter_name=c.consenter_name,
        consenter_relation=c.consenter_relation,
        document_ref=c.document_ref,
        decided_by=c.decided_by,
        decided_at=c.decided_at,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


@router.post("/tenants/{tenant_id}/consents", response_model=S.ConsentResponse)
def create_consent(
    tenant_id: uuid.UUID,
    body: S.ConsentCreateRequest,
    ctx: RequestContext = Depends(require(P.DENTAL_RECORD)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.ConsentResponse:
    match_tenant(ctx, tenant_id)
    c = dplans.create_consent(
        db,
        tenant_id=tenant_id,
        plan_id=body.plan_id,
        procedure_record_id=body.procedure_record_id,
        consenter_name=body.consenter_name,
        consenter_relation=body.consenter_relation,
        document_ref=body.document_ref,
        location_ids=ctx.location_ids,
    )
    _audit(db, ctx, action="consent.created", rtype="consent", rid=str(c.id))
    return _consent_resp(c)


@router.post("/tenants/{tenant_id}/consents/{consent_id}/decide", response_model=S.ConsentResponse)
def decide_consent(
    tenant_id: uuid.UUID,
    consent_id: uuid.UUID,
    body: S.ConsentDecideRequest,
    ctx: RequestContext = Depends(require(P.DENTAL_RECORD)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.ConsentResponse:
    match_tenant(ctx, tenant_id)
    c = dplans.decide_consent(
        db,
        tenant_id=tenant_id,
        consent_id=consent_id,
        decision=body.decision,
        actor_id=ctx.user_id,
        location_ids=ctx.location_ids,
    )
    _audit(db, ctx, action="consent.decided", rtype="consent", rid=str(c.id))
    return _consent_resp(c)


@router.post(
    "/tenants/{tenant_id}/consents/{consent_id}/withdraw", response_model=S.ConsentResponse
)
def withdraw_consent(
    tenant_id: uuid.UUID,
    consent_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.DENTAL_RECORD)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.ConsentResponse:
    match_tenant(ctx, tenant_id)
    c = dplans.withdraw_consent(
        db,
        tenant_id=tenant_id,
        consent_id=consent_id,
        actor_id=ctx.user_id,
        location_ids=ctx.location_ids,
    )
    _audit(db, ctx, action="consent.withdrawn", rtype="consent", rid=str(c.id))
    return _consent_resp(c)


def _recall_resp(r: Recall) -> S.RecallResponse:
    return S.RecallResponse(
        id=r.id,
        tenant_id=r.tenant_id,
        patient_id=r.patient_id,
        practitioner_id=r.practitioner_id,
        location_id=r.location_id,
        due_date=r.due_date,
        reason=r.reason,
        status=r.status,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


@router.post("/tenants/{tenant_id}/recalls", response_model=S.RecallResponse)
def create_recall(
    tenant_id: uuid.UUID,
    body: S.RecallCreateRequest,
    ctx: RequestContext = Depends(require(P.DENTAL_RECORD)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.RecallResponse:
    match_tenant(ctx, tenant_id)
    r = dplans.create_recall(
        db,
        tenant_id=tenant_id,
        actor_id=ctx.user_id,
        patient_id=body.patient_id,
        practitioner_id=body.practitioner_id,
        location_id=body.location_id,
        due_date=body.due_date,
        reason=body.reason,
        location_ids=ctx.location_ids,
    )
    _audit(db, ctx, action="recall.scheduled", rtype="recall", rid=str(r.id))
    return _recall_resp(r)


@router.get("/tenants/{tenant_id}/recalls", response_model=list[S.RecallResponse])
def list_recalls(
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.DENTAL_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> list[S.RecallResponse]:
    match_tenant(ctx, tenant_id)
    return [
        _recall_resp(r)
        for r in dplans.list_recalls(
            db, tenant_id=tenant_id, patient_id=patient_id, location_ids=ctx.location_ids
        )
    ]


@router.post("/tenants/{tenant_id}/recalls/{recall_id}/status", response_model=S.RecallResponse)
def transition_recall(
    tenant_id: uuid.UUID,
    recall_id: uuid.UUID,
    body: S.RecallStatusRequest,
    ctx: RequestContext = Depends(require(P.DENTAL_RECORD)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.RecallResponse:
    match_tenant(ctx, tenant_id)
    r = dplans.transition_recall(
        db,
        tenant_id=tenant_id,
        recall_id=recall_id,
        to_status=body.status,
        location_ids=ctx.location_ids,
    )
    _audit(db, ctx, action="recall.status", rtype="recall", rid=str(r.id))
    return _recall_resp(r)


def _docref_resp(d: DocumentReference) -> S.DocumentRefResponse:
    return S.DocumentRefResponse(
        id=d.id,
        tenant_id=d.tenant_id,
        encounter_id=d.encounter_id,
        doc_type=d.doc_type,
        storage_key=d.storage_key,
        content_type=d.content_type,
        size_bytes=d.size_bytes,
        sha256=d.sha256,
        notes=d.notes,
        created_at=d.created_at,
    )


@router.post(
    "/tenants/{tenant_id}/encounters/{encounter_id}/documents",
    response_model=S.DocumentRefResponse,
)
def create_document_ref(
    tenant_id: uuid.UUID,
    encounter_id: uuid.UUID,
    body: S.DocumentRefCreateRequest,
    ctx: RequestContext = Depends(require(P.DENTAL_RECORD)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.DocumentRefResponse:
    match_tenant(ctx, tenant_id)
    d = dplans.create_document_ref(
        db,
        tenant_id=tenant_id,
        encounter_id=encounter_id,
        actor_id=ctx.user_id,
        doc_type=body.doc_type,
        storage_key=body.storage_key,
        content_type=body.content_type,
        size_bytes=body.size_bytes,
        sha256=body.sha256,
        notes=body.notes,
        location_ids=ctx.location_ids,
    )
    _audit(db, ctx, action="document.referenced", rtype="document", rid=str(d.id))
    return _docref_resp(d)


@router.get(
    "/tenants/{tenant_id}/encounters/{encounter_id}/documents",
    response_model=list[S.DocumentRefResponse],
)
def list_document_refs(
    tenant_id: uuid.UUID,
    encounter_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.DENTAL_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> list[S.DocumentRefResponse]:
    match_tenant(ctx, tenant_id)
    return [
        _docref_resp(d)
        for d in dplans.list_document_refs(
            db, tenant_id=tenant_id, encounter_id=encounter_id, location_ids=ctx.location_ids
        )
    ]
