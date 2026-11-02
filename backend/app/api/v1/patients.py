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
from app.modules.patients.models import Patient
from app.platform.authz.permissions import P
from app.platform.authz.scope import RequestContext
from app.platform.request_context import request_id_ctx

router = APIRouter(tags=["patients"])


def _resp(p: Patient) -> S.PatientResponse:
    return S.PatientResponse(
        id=p.id,
        tenant_id=p.tenant_id,
        display_name=p.display_name,
        phone=p.phone,
        is_active=p.is_active,
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
    return _resp(patient)


@router.get("/tenants/{tenant_id}/patients", response_model=list[S.PatientResponse])
def list_patients(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.PATIENT_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    limit: int = 50,
) -> list[S.PatientResponse]:
    match_tenant(ctx, tenant_id)
    return [_resp(p) for p in patients_service.list_patients(db, tenant_id=tenant_id, limit=limit)]


@router.get("/tenants/{tenant_id}/patients/{patient_id}", response_model=S.PatientResponse)
def get_patient(
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.PATIENT_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.PatientResponse:
    match_tenant(ctx, tenant_id)
    return _resp(patients_service.get_patient(db, tenant_id=tenant_id, patient_id=patient_id))
