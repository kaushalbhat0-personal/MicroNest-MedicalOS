"""Patient identity endpoints. Thin adapters: tenant match + permission gate,
then straight into the patients service. No clinical data exists at this layer."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DBSession

from app.api.deps import get_db, require
from app.api.v1._shared import match_tenant
from app.modules.audit import service as audit_service
from app.modules.patients import schemas as S
from app.modules.patients import service as patients_service
from app.modules.patients import timeline as patient_timeline
from app.modules.patients.models import Patient
from app.platform.authz.permissions import P
from app.platform.authz.scope import RequestContext
from app.platform.request_context import request_id_ctx

router = APIRouter(tags=["patients"])


def _resp(p: Patient, *, duplicates: list[uuid.UUID] | None = None) -> S.PatientResponse:
    return S.PatientResponse(
        id=p.id,
        tenant_id=p.tenant_id,
        display_name=p.display_name,
        phone=p.phone,
        email=p.email,
        date_of_birth=p.date_of_birth,
        emergency_contact_name=p.emergency_contact_name,
        emergency_contact_phone=p.emergency_contact_phone,
        is_active=p.is_active,
        potential_duplicates=duplicates or [],
    )


@router.post("/tenants/{tenant_id}/patients", response_model=S.PatientResponse)
def register_patient(
    tenant_id: uuid.UUID,
    body: S.PatientCreateRequest,
    ctx: RequestContext = Depends(require(P.PATIENT_CREATE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.PatientResponse:
    match_tenant(ctx, tenant_id)
    patient = patients_service.register_patient(
        db,
        tenant_id=tenant_id,
        display_name=body.display_name,
        phone=body.phone,
        email=body.email,
        date_of_birth=body.date_of_birth,
        emergency_contact_name=body.emergency_contact_name,
        emergency_contact_phone=body.emergency_contact_phone,
    )
    dups = patients_service.find_potential_duplicates(
        db,
        tenant_id=tenant_id,
        phone=patient.phone,
        email=patient.email,
        exclude_id=patient.id,
    )
    audit_service.append(
        db,
        tenant_id=tenant_id,
        actor_type="user",
        actor_id=str(ctx.user_id),
        action="patient.register",
        resource_type="patient",
        resource_id=str(patient.id),
        request_id=request_id_ctx.get(),
    )
    return _resp(patient, duplicates=[d.id for d in dups])


@router.post("/tenants/{tenant_id}/patients/import", response_model=S.PatientImportResponse)
def import_patients(
    tenant_id: uuid.UUID,
    body: S.PatientImportRequest,
    ctx: RequestContext = Depends(require(P.PATIENT_CREATE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.PatientImportResponse:
    match_tenant(ctx, tenant_id)
    rows = [r.model_dump() for r in body.rows]
    created, skipped, errors, results = patients_service.import_patients(
        db, tenant_id=tenant_id, rows=rows
    )
    audit_service.append(
        db,
        tenant_id=tenant_id,
        actor_type="user",
        actor_id=str(ctx.user_id),
        action="patient.import",
        resource_type="patient",
        resource_id=str(tenant_id),
        request_id=request_id_ctx.get(),
    )
    mapped: list[S.PatientImportResultRow] = []
    for r in results:
        raw_row = r["row"]
        raw_pid = r.get("patient_id")
        mapped.append(
            S.PatientImportResultRow(
                row=raw_row if isinstance(raw_row, int) else int(str(raw_row)),
                status=str(r["status"]),
                patient_id=raw_pid if isinstance(raw_pid, uuid.UUID) else None,
                message=None if r.get("message") is None else str(r["message"]),
            )
        )
    return S.PatientImportResponse(
        created=created,
        skipped=skipped,
        errors=errors,
        results=mapped,
    )


@router.get("/tenants/{tenant_id}/patients", response_model=list[S.PatientResponse])
def list_patients(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.PATIENT_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    limit: int = 50,
    q: str | None = None,
    active_only: bool = False,
) -> list[S.PatientResponse]:
    match_tenant(ctx, tenant_id)
    return [
        _resp(p)
        for p in patients_service.list_patients(
            db, tenant_id=tenant_id, limit=limit, q=q, active_only=active_only
        )
    ]


@router.get("/tenants/{tenant_id}/patients/{patient_id}", response_model=S.PatientResponse)
def get_patient(
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.PATIENT_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.PatientResponse:
    match_tenant(ctx, tenant_id)
    return _resp(patients_service.get_patient(db, tenant_id=tenant_id, patient_id=patient_id))


@router.patch("/tenants/{tenant_id}/patients/{patient_id}", response_model=S.PatientResponse)
def patch_patient(
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    body: S.PatientUpdateRequest,
    ctx: RequestContext = Depends(require(P.PATIENT_UPDATE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.PatientResponse:
    match_tenant(ctx, tenant_id)
    fields = body.model_dump(exclude_unset=True)
    patient = patients_service.apply_patient_patch(
        db, tenant_id=tenant_id, patient_id=patient_id, fields=fields
    )
    dups = patients_service.find_potential_duplicates(
        db,
        tenant_id=tenant_id,
        phone=patient.phone,
        email=patient.email,
        exclude_id=patient.id,
    )
    audit_service.append(
        db,
        tenant_id=tenant_id,
        actor_type="user",
        actor_id=str(ctx.user_id),
        action="patient.update",
        resource_type="patient",
        resource_id=str(patient.id),
        request_id=request_id_ctx.get(),
    )
    return _resp(patient, duplicates=[d.id for d in dups])


def _overview_resp(o: patient_timeline.PatientOverview) -> S.PatientOverviewResponse:
    return S.PatientOverviewResponse(
        patient_id=o.patient_id,
        display_name=o.display_name,
        phone=o.phone,
        email=o.email,
        date_of_birth=o.date_of_birth,
        is_active=o.is_active,
        last_visit_at=o.last_visit_at,
        next_appointment_at=o.next_appointment_at,
        next_appointment_id=o.next_appointment_id,
        outstanding_balance=o.outstanding_balance,
        currency=o.currency,
        follow_up_due=o.follow_up_due,
        open_followups=o.open_followups,
        overdue_followups=o.overdue_followups,
        completed_followups=o.completed_followups,
    )


def _timeline_item(item: patient_timeline.TimelineItem) -> S.TimelineItemResponse:
    return S.TimelineItemResponse(
        event_id=item.event_id,
        kind=item.kind,
        category=item.category,
        occurred_at=item.occurred_at,
        title=item.title,
        summary=item.summary,
        resource_type=item.resource_type,
        resource_id=item.resource_id,
        location_id=item.location_id,
        status=item.status,
        href=item.href,
    )


@router.get(
    "/tenants/{tenant_id}/patients/{patient_id}/overview",
    response_model=S.PatientOverviewResponse,
)
def patient_overview(
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.PATIENT_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.PatientOverviewResponse:
    match_tenant(ctx, tenant_id)
    overview = patient_timeline.build_overview(
        db,
        tenant_id=tenant_id,
        patient_id=patient_id,
        location_ids=ctx.location_ids or None,
    )
    return _overview_resp(overview)


@router.get(
    "/tenants/{tenant_id}/patients/{patient_id}/timeline",
    response_model=S.TimelinePageResponse,
)
def patient_timeline_page(
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.PATIENT_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    category: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> S.TimelinePageResponse:
    match_tenant(ctx, tenant_id)
    cat: patient_timeline.Category | None = None
    if category is not None:
        allowed = {"admin", "scheduling", "clinical", "billing", "documents", "care"}
        if category not in allowed:
            from app.platform.errors import ValidationError

            raise ValidationError("unknown timeline category")
        cat = category  # type: ignore[assignment]
    items, next_cursor = patient_timeline.build_timeline(
        db,
        tenant_id=tenant_id,
        patient_id=patient_id,
        audience="staff",
        category=cat,
        location_ids=ctx.location_ids or None,
        limit=limit,
        cursor=cursor,
    )
    return S.TimelinePageResponse(
        items=[_timeline_item(i) for i in items],
        next_cursor=next_cursor,
    )
