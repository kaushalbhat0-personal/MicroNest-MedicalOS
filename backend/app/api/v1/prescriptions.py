"""Prescription endpoints. Item content is clinical: responses carry it to
authorized readers, but audit entries carry opaque IDs only. Signing and
correction rules live in the service."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DBSession

from app.api.deps import get_db, require
from app.api.v1._shared import match_tenant, practitioner_for_user
from app.modules.audit import service as audit_service
from app.modules.prescriptions import schemas as S
from app.modules.prescriptions import service as rx
from app.modules.prescriptions.models import Medication, Prescription, PrescriptionItem
from app.platform.authz.permissions import P
from app.platform.authz.scope import RequestContext
from app.platform.request_context import request_id_ctx

router = APIRouter(tags=["prescriptions"])


def _audit(db: DBSession, ctx: RequestContext, *, action: str, rid: str) -> None:
    audit_service.append(
        db,
        tenant_id=ctx.tenant_id,
        actor_type="user",
        actor_id=str(ctx.user_id),
        action=action,
        resource_type="prescription",
        resource_id=rid,
        request_id=request_id_ctx.get(),
    )


def _item_resp(db: DBSession, item: PrescriptionItem) -> S.PrescriptionItemResponse:
    med = db.get(Medication, item.medication_id)
    assert med is not None
    return S.PrescriptionItemResponse(
        id=item.id,
        medication_code=med.code,
        medication_name=med.name,
        line_no=item.line_no,
        dose=item.dose,
        route=item.route,
        frequency=item.frequency,
        duration_days=item.duration_days,
        quantity=float(item.quantity) if item.quantity is not None else None,
        instructions=item.instructions,
    )


def _resp(db: DBSession, p: Prescription) -> S.PrescriptionResponse:
    from sqlalchemy import select

    items = (
        db.execute(
            select(PrescriptionItem)
            .where(PrescriptionItem.prescription_id == p.id)
            .order_by(PrescriptionItem.line_no)
        )
        .scalars()
        .all()
    )
    return S.PrescriptionResponse(
        id=p.id,
        tenant_id=p.tenant_id,
        encounter_id=p.encounter_id,
        prescribed_by=p.prescribed_by,
        status=p.status,
        version=p.version,
        supersedes_id=p.supersedes_id,
        superseded_by_id=p.superseded_by_id,
        signed_by=p.signed_by,
        signed_at=p.signed_at,
        cancelled_by=p.cancelled_by,
        cancelled_at=p.cancelled_at,
        cancel_reason=p.cancel_reason,
        items=[_item_resp(db, i) for i in items],
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


@router.get("/tenants/{tenant_id}/medications", response_model=list[S.MedicationResponse])
def list_medications(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.PRESCRIPTION_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> list[S.MedicationResponse]:
    match_tenant(ctx, tenant_id)
    return [
        S.MedicationResponse(
            id=m.id,
            code=m.code,
            name=m.name,
            generic_name=m.generic_name,
            strength=m.strength,
            dosage_form=m.dosage_form,
            atc=m.atc,
            is_active=m.is_active,
        )
        for m in rx.list_medications(db)
    ]


@router.post(
    "/tenants/{tenant_id}/encounters/{encounter_id}/prescriptions",
    response_model=S.PrescriptionResponse,
)
def create_prescription(
    tenant_id: uuid.UUID,
    encounter_id: uuid.UUID,
    body: S.PrescriptionCreateRequest,
    ctx: RequestContext = Depends(require(P.PRESCRIPTION_CREATE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.PrescriptionResponse:
    match_tenant(ctx, tenant_id)
    prescriber = practitioner_for_user(db, ctx.user_id)
    p = rx.create_prescription(
        db,
        tenant_id=tenant_id,
        encounter_id=encounter_id,
        prescribed_by=prescriber.id,
        items=[i.model_dump() for i in body.items],
        location_ids=ctx.location_ids,
    )
    _audit(db, ctx, action="prescription.created", rid=str(p.id))
    return _resp(db, p)


@router.get(
    "/tenants/{tenant_id}/encounters/{encounter_id}/prescriptions",
    response_model=list[S.PrescriptionResponse],
)
def list_prescriptions(
    tenant_id: uuid.UUID,
    encounter_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.PRESCRIPTION_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> list[S.PrescriptionResponse]:
    match_tenant(ctx, tenant_id)
    return [
        _resp(db, p)
        for p in rx.list_prescriptions(
            db, tenant_id=tenant_id, encounter_id=encounter_id, location_ids=ctx.location_ids
        )
    ]


@router.get(
    "/tenants/{tenant_id}/prescriptions/{prescription_id}",
    response_model=S.PrescriptionResponse,
)
def get_prescription(
    tenant_id: uuid.UUID,
    prescription_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.PRESCRIPTION_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.PrescriptionResponse:
    match_tenant(ctx, tenant_id)
    return _resp(
        db,
        rx.get_prescription(
            db,
            tenant_id=tenant_id,
            prescription_id=prescription_id,
            location_ids=ctx.location_ids,
        ),
    )


@router.post(
    "/tenants/{tenant_id}/prescriptions/{prescription_id}/sign",
    response_model=S.PrescriptionResponse,
)
def sign_prescription(
    tenant_id: uuid.UUID,
    prescription_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.PRESCRIPTION_SIGN)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.PrescriptionResponse:
    match_tenant(ctx, tenant_id)
    prescriber = practitioner_for_user(db, ctx.user_id)
    p = rx.sign_prescription(
        db,
        tenant_id=tenant_id,
        prescription_id=prescription_id,
        actor_id=prescriber.id,
        location_ids=ctx.location_ids,
    )
    _audit(db, ctx, action="prescription.signed", rid=str(p.id))
    return _resp(db, p)


@router.post(
    "/tenants/{tenant_id}/prescriptions/{prescription_id}/cancel",
    response_model=S.PrescriptionResponse,
)
def cancel_prescription(
    tenant_id: uuid.UUID,
    prescription_id: uuid.UUID,
    body: S.PrescriptionCancelRequest,
    ctx: RequestContext = Depends(require(P.PRESCRIPTION_SIGN)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.PrescriptionResponse:
    match_tenant(ctx, tenant_id)
    prescriber = practitioner_for_user(db, ctx.user_id)
    p = rx.cancel_prescription(
        db,
        tenant_id=tenant_id,
        prescription_id=prescription_id,
        actor_id=prescriber.id,
        reason=body.reason,
        location_ids=ctx.location_ids,
    )
    _audit(db, ctx, action="prescription.cancelled", rid=str(p.id))
    return _resp(db, p)


@router.post(
    "/tenants/{tenant_id}/prescriptions/{prescription_id}/correct",
    response_model=S.PrescriptionResponse,
)
def correct_prescription(
    tenant_id: uuid.UUID,
    prescription_id: uuid.UUID,
    body: S.PrescriptionCreateRequest,
    ctx: RequestContext = Depends(require(P.PRESCRIPTION_CREATE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.PrescriptionResponse:
    match_tenant(ctx, tenant_id)
    prescriber = practitioner_for_user(db, ctx.user_id)
    p = rx.correct_prescription(
        db,
        tenant_id=tenant_id,
        prescription_id=prescription_id,
        prescribed_by=prescriber.id,
        items=[i.model_dump() for i in body.items],
        location_ids=ctx.location_ids,
    )
    _audit(db, ctx, action="prescription.corrected", rid=str(p.id))
    return _resp(db, p)
