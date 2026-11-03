"""Service catalog endpoints. Global charge master: reads are tenant-scoped
only for authorization, never for filtering. Writes require billing.config.
Audit entries carry opaque IDs only."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session as DBSession

from app.api.deps import get_db, require
from app.api.v1._shared import match_tenant
from app.modules.audit import service as audit_service
from app.modules.billing import credit_notes as billing_credit_notes
from app.modules.billing import estimates as billing_estimates
from app.modules.billing import invoices as billing_invoices
from app.modules.billing import payments as billing_payments
from app.modules.billing import receipts as billing_receipts
from app.modules.billing import refunds as billing_refunds
from app.modules.billing import schemas as S
from app.modules.billing import service_catalog as catalog
from app.modules.billing.models import (
    CreditNote,
    Estimate,
    EstimateLine,
    Invoice,
    InvoiceLine,
    Payment,
    PaymentAllocation,
    Receipt,
    Refund,
    ServiceCatalogItem,
)
from app.platform.authz.permissions import P
from app.platform.authz.scope import RequestContext
from app.platform.request_context import request_id_ctx

router = APIRouter(tags=["billing"])


def _audit(db: DBSession, ctx: RequestContext, *, action: str, rid: str) -> None:
    audit_service.append(
        db,
        tenant_id=ctx.tenant_id,
        actor_type="user",
        actor_id=str(ctx.user_id),
        action=action,
        resource_type="service_catalog",
        resource_id=rid,
        request_id=request_id_ctx.get(),
    )


def _estimate_audit(db: DBSession, ctx: RequestContext, *, action: str, rid: str) -> None:
    audit_service.append(
        db,
        tenant_id=ctx.tenant_id,
        actor_type="user",
        actor_id=str(ctx.user_id),
        action=action,
        resource_type="estimate",
        resource_id=rid,
        request_id=request_id_ctx.get(),
    )


def _invoice_audit(db: DBSession, ctx: RequestContext, *, action: str, rid: str) -> None:
    audit_service.append(
        db,
        tenant_id=ctx.tenant_id,
        actor_type="user",
        actor_id=str(ctx.user_id),
        action=action,
        resource_type="invoice",
        resource_id=rid,
        request_id=request_id_ctx.get(),
    )


def _resp(item: ServiceCatalogItem) -> S.ServiceCatalogResponse:
    return S.ServiceCatalogResponse(
        id=item.id,
        code=item.code,
        display=item.display,
        description=item.description,
        default_rate=str(item.default_rate),
        currency=item.currency,
        hsn_sac=item.hsn_sac,
        tax_rate=str(item.tax_rate),
        is_active=item.is_active,
    )


@router.get("/tenants/{tenant_id}/service-catalog", response_model=S.ServiceCatalogListResponse)
def list_services(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.BILLING_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    active: bool | None = None,
    search: str | None = None,
    limit: int = 50,
    cursor: uuid.UUID | None = None,
) -> S.ServiceCatalogListResponse:
    match_tenant(ctx, tenant_id)
    items, next_cursor = catalog.list_services(
        db, active=active, search=search, limit=limit, cursor=cursor
    )
    return S.ServiceCatalogListResponse(items=[_resp(i) for i in items], next_cursor=next_cursor)


@router.get(
    "/tenants/{tenant_id}/service-catalog/{item_id}",
    response_model=S.ServiceCatalogResponse,
)
def get_service(
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.BILLING_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.ServiceCatalogResponse:
    match_tenant(ctx, tenant_id)
    return _resp(catalog.get_service(db, item_id=item_id))


@router.post("/tenants/{tenant_id}/service-catalog", response_model=S.ServiceCatalogResponse)
def create_service(
    tenant_id: uuid.UUID,
    body: S.ServiceCatalogCreateRequest,
    ctx: RequestContext = Depends(require(P.BILLING_CONFIG)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.ServiceCatalogResponse:
    match_tenant(ctx, tenant_id)
    item = catalog.create_service(
        db,
        code=body.code,
        display=body.display,
        description=body.description,
        default_rate=body.default_rate,
        currency=body.currency,
        hsn_sac=body.hsn_sac,
        tax_rate=body.tax_rate,
    )
    _audit(db, ctx, action="service_catalog.created", rid=str(item.id))
    return _resp(item)


@router.patch(
    "/tenants/{tenant_id}/service-catalog/{item_id}",
    response_model=S.ServiceCatalogResponse,
)
def update_service(
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    body: S.ServiceCatalogUpdateRequest,
    ctx: RequestContext = Depends(require(P.BILLING_CONFIG)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.ServiceCatalogResponse:
    match_tenant(ctx, tenant_id)
    item = catalog.update_service(
        db,
        item_id=item_id,
        display=body.display,
        description=body.description,
        default_rate=body.default_rate,
        tax_rate=body.tax_rate,
        hsn_sac=body.hsn_sac,
        currency=body.currency,
    )
    _audit(db, ctx, action="service_catalog.updated", rid=str(item.id))
    return _resp(item)


@router.post(
    "/tenants/{tenant_id}/service-catalog/{item_id}/activate",
    response_model=S.ServiceCatalogResponse,
)
def activate_service(
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.BILLING_CONFIG)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.ServiceCatalogResponse:
    match_tenant(ctx, tenant_id)
    item = catalog.set_active(db, item_id=item_id, is_active=True)
    _audit(db, ctx, action="service_catalog.activated", rid=str(item.id))
    return _resp(item)


@router.post(
    "/tenants/{tenant_id}/service-catalog/{item_id}/deactivate",
    response_model=S.ServiceCatalogResponse,
)
def deactivate_service(
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.BILLING_CONFIG)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.ServiceCatalogResponse:
    match_tenant(ctx, tenant_id)
    item = catalog.set_active(db, item_id=item_id, is_active=False)
    _audit(db, ctx, action="service_catalog.deactivated", rid=str(item.id))
    return _resp(item)


def _line_resp(line: EstimateLine) -> S.EstimateLineResponse:
    return S.EstimateLineResponse(
        id=line.id,
        service_catalog_id=line.service_catalog_id,
        description=line.description,
        quantity=str(line.quantity),
        unit_rate=str(line.unit_rate),
        discount_amount=str(line.discount_amount),
        taxable_amount=str(line.taxable_amount),
        tax_rate=str(line.tax_rate),
        tax_amount=str(line.tax_amount),
        hsn_sac=line.hsn_sac,
        tax_treatment=line.tax_treatment,
        line_total=str(line.line_total),
        sequence=line.sequence,
    )


def _estimate_resp(db: DBSession, est: Estimate) -> S.EstimateResponse:
    return S.EstimateResponse(
        id=est.id,
        tenant_id=est.tenant_id,
        location_id=est.location_id,
        patient_id=est.patient_id,
        encounter_id=est.encounter_id,
        treatment_plan_id=est.treatment_plan_id,
        practitioner_id=est.practitioner_id,
        status=est.status,
        version=est.version,
        currency=est.currency,
        subtotal=str(est.subtotal),
        tax_total=str(est.tax_total),
        grand_total=str(est.grand_total),
        valid_until=est.valid_until,
        notes=est.notes,
        lines=[
            _line_resp(line) for line in billing_estimates.estimate_lines(db, estimate_id=est.id)
        ],
        created_at=est.created_at,
        updated_at=est.updated_at,
    )


@router.post("/tenants/{tenant_id}/estimates", response_model=S.EstimateResponse)
def create_estimate(
    tenant_id: uuid.UUID,
    body: S.EstimateCreateRequest,
    ctx: RequestContext = Depends(require(P.BILLING_CREATE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.EstimateResponse:
    match_tenant(ctx, tenant_id)
    est = billing_estimates.create_estimate(
        db,
        tenant_id=tenant_id,
        actor_id=ctx.user_id,
        patient_id=body.patient_id,
        location_id=body.location_id,
        practitioner_id=body.practitioner_id,
        encounter_id=body.encounter_id,
        treatment_plan_id=body.treatment_plan_id,
        valid_until=body.valid_until,
        notes=body.notes,
        items=[i.model_dump() for i in body.items],
        idempotency_key=body.idempotency_key,
        location_ids=ctx.location_ids,
    )
    _estimate_audit(db, ctx, action="estimate.created", rid=str(est.id))
    return _estimate_resp(db, est)


@router.get("/tenants/{tenant_id}/estimates", response_model=S.EstimateListResponse)
def list_estimates(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.BILLING_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    patient_id: uuid.UUID | None = None,
    status: str | None = None,
    limit: int = 50,
    cursor: uuid.UUID | None = None,
) -> S.EstimateListResponse:
    match_tenant(ctx, tenant_id)
    items, next_cursor = billing_estimates.list_estimates(
        db,
        tenant_id=tenant_id,
        patient_id=patient_id,
        status=status,
        location_ids=ctx.location_ids,
        limit=limit,
        cursor=cursor,
    )
    return S.EstimateListResponse(
        items=[_estimate_resp(db, e) for e in items], next_cursor=next_cursor
    )


@router.get("/tenants/{tenant_id}/estimates/{estimate_id}", response_model=S.EstimateResponse)
def get_estimate(
    tenant_id: uuid.UUID,
    estimate_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.BILLING_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.EstimateResponse:
    match_tenant(ctx, tenant_id)
    return _estimate_resp(
        db,
        billing_estimates.get_estimate(
            db, tenant_id=tenant_id, estimate_id=estimate_id, location_ids=ctx.location_ids
        ),
    )


@router.patch("/tenants/{tenant_id}/estimates/{estimate_id}", response_model=S.EstimateResponse)
def update_estimate(
    tenant_id: uuid.UUID,
    estimate_id: uuid.UUID,
    body: S.EstimateUpdateRequest,
    ctx: RequestContext = Depends(require(P.BILLING_CREATE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.EstimateResponse:
    match_tenant(ctx, tenant_id)
    est = billing_estimates.update_estimate(
        db,
        tenant_id=tenant_id,
        estimate_id=estimate_id,
        notes=body.notes,
        valid_until=body.valid_until,
        location_ids=ctx.location_ids,
    )
    _estimate_audit(db, ctx, action="estimate.updated", rid=str(est.id))
    return _estimate_resp(db, est)


@router.post(
    "/tenants/{tenant_id}/estimates/{estimate_id}/lines",
    response_model=S.EstimateLineResponse,
)
def add_estimate_line(
    tenant_id: uuid.UUID,
    estimate_id: uuid.UUID,
    body: S.EstimateLineRequest,
    ctx: RequestContext = Depends(require(P.BILLING_CREATE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.EstimateLineResponse:
    match_tenant(ctx, tenant_id)
    line = billing_estimates.add_estimate_line(
        db,
        tenant_id=tenant_id,
        estimate_id=estimate_id,
        location_ids=ctx.location_ids,
        **body.model_dump(),
    )
    _estimate_audit(db, ctx, action="estimate.updated", rid=str(estimate_id))
    return _line_resp(line)


@router.patch(
    "/tenants/{tenant_id}/estimate-lines/{line_id}",
    response_model=S.EstimateLineResponse,
)
def update_estimate_line(
    tenant_id: uuid.UUID,
    line_id: uuid.UUID,
    body: S.EstimateLineUpdateRequest,
    ctx: RequestContext = Depends(require(P.BILLING_CREATE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.EstimateLineResponse:
    match_tenant(ctx, tenant_id)
    line = billing_estimates.update_estimate_line(
        db,
        tenant_id=tenant_id,
        line_id=line_id,
        location_ids=ctx.location_ids,
        **{k: v for k, v in body.model_dump().items() if v is not None},
    )
    _estimate_audit(db, ctx, action="estimate.updated", rid=str(line.estimate_id))
    return _line_resp(line)


@router.delete(
    "/tenants/{tenant_id}/estimate-lines/{line_id}",
    response_model=S.EstimateResponse,
)
def remove_estimate_line(
    tenant_id: uuid.UUID,
    line_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.BILLING_CREATE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.EstimateResponse:
    match_tenant(ctx, tenant_id)
    est = billing_estimates.remove_estimate_line(
        db, tenant_id=tenant_id, line_id=line_id, location_ids=ctx.location_ids
    )
    _estimate_audit(db, ctx, action="estimate.updated", rid=str(est.id))
    return _estimate_resp(db, est)


@router.post(
    "/tenants/{tenant_id}/estimates/{estimate_id}/issue",
    response_model=S.EstimateResponse,
)
def issue_estimate(
    tenant_id: uuid.UUID,
    estimate_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.BILLING_CREATE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.EstimateResponse:
    match_tenant(ctx, tenant_id)
    est = billing_estimates.issue_estimate(
        db,
        tenant_id=tenant_id,
        estimate_id=estimate_id,
        actor_id=ctx.user_id,
        location_ids=ctx.location_ids,
    )
    _estimate_audit(db, ctx, action="estimate.issued", rid=str(est.id))
    return _estimate_resp(db, est)


@router.post(
    "/tenants/{tenant_id}/estimates/{estimate_id}/cancel",
    response_model=S.EstimateResponse,
)
def cancel_estimate(
    tenant_id: uuid.UUID,
    estimate_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.BILLING_CREATE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.EstimateResponse:
    match_tenant(ctx, tenant_id)
    est = billing_estimates.cancel_estimate(
        db, tenant_id=tenant_id, estimate_id=estimate_id, location_ids=ctx.location_ids
    )
    _estimate_audit(db, ctx, action="estimate.cancelled", rid=str(est.id))
    return _estimate_resp(db, est)


@router.post(
    "/tenants/{tenant_id}/estimates/{estimate_id}/expire",
    response_model=S.EstimateResponse,
)
def expire_estimate(
    tenant_id: uuid.UUID,
    estimate_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.BILLING_CREATE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.EstimateResponse:
    match_tenant(ctx, tenant_id)
    est = billing_estimates.expire_estimate(
        db, tenant_id=tenant_id, estimate_id=estimate_id, location_ids=ctx.location_ids
    )
    _estimate_audit(db, ctx, action="estimate.expired", rid=str(est.id))
    return _estimate_resp(db, est)


def _invoice_line_resp(line: InvoiceLine) -> S.InvoiceLineResponse:
    return S.InvoiceLineResponse(
        id=line.id,
        source_estimate_line_id=line.source_estimate_line_id,
        description=line.description,
        quantity=str(line.quantity),
        unit_rate=str(line.unit_rate),
        discount_amount=str(line.discount_amount),
        taxable_amount=str(line.taxable_amount),
        tax_rate=str(line.tax_rate),
        tax_amount=str(line.tax_amount),
        hsn_sac=line.hsn_sac,
        tax_treatment=line.tax_treatment,
        line_total=str(line.line_total),
        sequence=line.sequence,
    )


def _invoice_resp(db: DBSession, inv: Invoice) -> S.InvoiceResponse:
    allocated = billing_invoices.effective_allocated(db, invoice_id=inv.id)
    outstanding = billing_invoices.outstanding_for_invoice(db, invoice=inv)
    return S.InvoiceResponse(
        id=inv.id,
        tenant_id=inv.tenant_id,
        location_id=inv.location_id,
        patient_id=inv.patient_id,
        encounter_id=inv.encounter_id,
        source_estimate_id=inv.source_estimate_id,
        status=inv.status,
        version=inv.version,
        currency=inv.currency,
        subtotal=str(inv.subtotal),
        tax_total=str(inv.tax_total),
        grand_total=str(inv.grand_total),
        allocated_amount=str(allocated),
        outstanding_amount=str(outstanding),
        financial_year=inv.financial_year,
        doc_number=inv.doc_number,
        due_date=inv.due_date,
        notes=inv.notes,
        lines=[
            _invoice_line_resp(line)
            for line in billing_invoices.invoice_lines(db, invoice_id=inv.id)
        ],
        created_at=inv.created_at,
        updated_at=inv.updated_at,
    )


@router.post("/tenants/{tenant_id}/invoices", response_model=S.InvoiceResponse)
def create_invoice(
    tenant_id: uuid.UUID,
    body: S.InvoiceCreateRequest,
    ctx: RequestContext = Depends(require(P.BILLING_CREATE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> S.InvoiceResponse:
    match_tenant(ctx, tenant_id)
    inv = billing_invoices.create_invoice(
        db,
        tenant_id=tenant_id,
        actor_id=ctx.user_id,
        patient_id=body.patient_id,
        location_id=body.location_id,
        encounter_id=body.encounter_id,
        due_date=body.due_date,
        notes=body.notes,
        currency=body.currency,
        items=[i.model_dump() for i in body.items],
        idempotency_key=idempotency_key or body.idempotency_key,
        location_ids=ctx.location_ids,
    )
    _invoice_audit(db, ctx, action="invoice.created", rid=str(inv.id))
    return _invoice_resp(db, inv)


@router.get("/tenants/{tenant_id}/invoices", response_model=S.InvoiceListResponse)
def list_invoices(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.BILLING_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    patient_id: uuid.UUID | None = None,
    status: str | None = None,
    limit: int = 50,
    cursor: uuid.UUID | None = None,
) -> S.InvoiceListResponse:
    match_tenant(ctx, tenant_id)
    items, next_cursor = billing_invoices.list_invoices(
        db,
        tenant_id=tenant_id,
        patient_id=patient_id,
        status=status,
        location_ids=ctx.location_ids,
        limit=limit,
        cursor=cursor,
    )
    return S.InvoiceListResponse(
        items=[_invoice_resp(db, i) for i in items], next_cursor=next_cursor
    )


@router.get("/tenants/{tenant_id}/invoices/{invoice_id}", response_model=S.InvoiceResponse)
def get_invoice(
    tenant_id: uuid.UUID,
    invoice_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.BILLING_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.InvoiceResponse:
    match_tenant(ctx, tenant_id)
    return _invoice_resp(
        db,
        billing_invoices.get_invoice(
            db, tenant_id=tenant_id, invoice_id=invoice_id, location_ids=ctx.location_ids
        ),
    )


@router.patch("/tenants/{tenant_id}/invoices/{invoice_id}", response_model=S.InvoiceResponse)
def update_invoice(
    tenant_id: uuid.UUID,
    invoice_id: uuid.UUID,
    body: S.InvoiceUpdateRequest,
    ctx: RequestContext = Depends(require(P.BILLING_CREATE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.InvoiceResponse:
    match_tenant(ctx, tenant_id)
    inv = billing_invoices.update_invoice(
        db,
        tenant_id=tenant_id,
        invoice_id=invoice_id,
        notes=body.notes,
        due_date=body.due_date,
        clear_due_date=body.clear_due_date,
        location_ids=ctx.location_ids,
    )
    _invoice_audit(db, ctx, action="invoice.updated", rid=str(inv.id))
    return _invoice_resp(db, inv)


@router.post(
    "/tenants/{tenant_id}/invoices/{invoice_id}/lines",
    response_model=S.InvoiceLineResponse,
)
def add_invoice_line(
    tenant_id: uuid.UUID,
    invoice_id: uuid.UUID,
    body: S.InvoiceLineRequest,
    ctx: RequestContext = Depends(require(P.BILLING_CREATE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.InvoiceLineResponse:
    match_tenant(ctx, tenant_id)
    line = billing_invoices.add_invoice_line(
        db,
        tenant_id=tenant_id,
        invoice_id=invoice_id,
        location_ids=ctx.location_ids,
        **body.model_dump(),
    )
    _invoice_audit(db, ctx, action="invoice.updated", rid=str(invoice_id))
    return _invoice_line_resp(line)


@router.patch(
    "/tenants/{tenant_id}/invoice-lines/{line_id}",
    response_model=S.InvoiceLineResponse,
)
def update_invoice_line(
    tenant_id: uuid.UUID,
    line_id: uuid.UUID,
    body: S.InvoiceLineUpdateRequest,
    ctx: RequestContext = Depends(require(P.BILLING_CREATE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.InvoiceLineResponse:
    match_tenant(ctx, tenant_id)
    line = billing_invoices.update_invoice_line(
        db,
        tenant_id=tenant_id,
        line_id=line_id,
        location_ids=ctx.location_ids,
        **{k: v for k, v in body.model_dump().items() if v is not None},
    )
    _invoice_audit(db, ctx, action="invoice.updated", rid=str(line.invoice_id))
    return _invoice_line_resp(line)


@router.delete(
    "/tenants/{tenant_id}/invoice-lines/{line_id}",
    response_model=S.InvoiceResponse,
)
def remove_invoice_line(
    tenant_id: uuid.UUID,
    line_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.BILLING_CREATE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.InvoiceResponse:
    match_tenant(ctx, tenant_id)
    inv = billing_invoices.remove_invoice_line(
        db, tenant_id=tenant_id, line_id=line_id, location_ids=ctx.location_ids
    )
    _invoice_audit(db, ctx, action="invoice.updated", rid=str(inv.id))
    return _invoice_resp(db, inv)


@router.post(
    "/tenants/{tenant_id}/invoices/{invoice_id}/issue",
    response_model=S.InvoiceResponse,
)
def issue_invoice(
    tenant_id: uuid.UUID,
    invoice_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.INVOICE_ISSUE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.InvoiceResponse:
    match_tenant(ctx, tenant_id)
    inv = billing_invoices.issue_invoice(
        db,
        tenant_id=tenant_id,
        invoice_id=invoice_id,
        actor_id=ctx.user_id,
        location_ids=ctx.location_ids,
    )
    _invoice_audit(db, ctx, action="invoice.issued", rid=str(inv.id))
    return _invoice_resp(db, inv)


@router.post(
    "/tenants/{tenant_id}/invoices/{invoice_id}/void",
    response_model=S.InvoiceResponse,
)
def void_invoice(
    tenant_id: uuid.UUID,
    invoice_id: uuid.UUID,
    body: S.InvoiceVoidRequest,
    ctx: RequestContext = Depends(require(P.INVOICE_ISSUE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.InvoiceResponse:
    match_tenant(ctx, tenant_id)
    inv = billing_invoices.void_invoice(
        db,
        tenant_id=tenant_id,
        invoice_id=invoice_id,
        actor_id=ctx.user_id,
        reason=body.reason,
        location_ids=ctx.location_ids,
    )
    _invoice_audit(db, ctx, action="invoice.voided", rid=str(inv.id))
    return _invoice_resp(db, inv)


@router.post(
    "/tenants/{tenant_id}/estimates/{estimate_id}/convert",
    response_model=S.InvoiceResponse,
)
def convert_estimate(
    tenant_id: uuid.UUID,
    estimate_id: uuid.UUID,
    body: S.ConvertEstimateRequest,
    ctx: RequestContext = Depends(require(P.BILLING_CREATE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> S.InvoiceResponse:
    match_tenant(ctx, tenant_id)
    inv = billing_invoices.convert_estimate_to_invoice(
        db,
        tenant_id=tenant_id,
        estimate_id=estimate_id,
        actor_id=ctx.user_id,
        line_ids=body.line_ids,
        notes=body.notes,
        due_date=body.due_date,
        idempotency_key=idempotency_key or body.idempotency_key,
        location_ids=ctx.location_ids,
    )
    _invoice_audit(db, ctx, action="invoice.created", rid=str(inv.id))
    _estimate_audit(db, ctx, action="estimate.converted", rid=str(estimate_id))
    return _invoice_resp(db, inv)


def _payment_audit(db: DBSession, ctx: RequestContext, *, action: str, rid: str) -> None:
    audit_service.append(
        db,
        tenant_id=ctx.tenant_id,
        actor_type="user",
        actor_id=str(ctx.user_id),
        action=action,
        resource_type="payment",
        resource_id=rid,
        request_id=request_id_ctx.get(),
    )


def _allocation_audit(
    db: DBSession, ctx: RequestContext, *, action: str, rid: str, reason: str | None = None
) -> None:
    audit_service.append(
        db,
        tenant_id=ctx.tenant_id,
        actor_type="user",
        actor_id=str(ctx.user_id),
        action=action,
        resource_type="allocation",
        resource_id=rid,
        request_id=request_id_ctx.get(),
        reason=reason,
    )


def _payment_resp(db: DBSession, payment: Payment) -> S.PaymentResponse:
    return S.PaymentResponse(
        id=payment.id,
        tenant_id=payment.tenant_id,
        location_id=payment.location_id,
        patient_id=payment.patient_id,
        encounter_id=payment.encounter_id,
        status=payment.status,
        method=payment.method,
        amount=str(payment.amount),
        allocated_amount=str(billing_payments.allocated_for_payment(db, payment=payment)),
        unallocated_amount=str(billing_payments.unallocated_for_payment(db, payment=payment)),
        currency=payment.currency,
        received_at=payment.received_at,
        provider_ref=payment.provider_ref,
        created_at=payment.created_at,
        updated_at=payment.updated_at,
    )


def _allocation_resp(db: DBSession, row: PaymentAllocation) -> S.AllocationResponse:
    reversed_ids = {
        r.reversal_of_id
        for r in billing_payments.payment_allocations(db, payment_id=row.payment_id)
        if r.reversal_of_id is not None
    }
    return S.AllocationResponse(
        id=row.id,
        payment_id=row.payment_id,
        invoice_id=row.invoice_id,
        amount=str(row.amount),
        reversal_of_id=row.reversal_of_id,
        reversed=row.id in reversed_ids,
        idempotency_key=row.idempotency_key,
    )


@router.post("/tenants/{tenant_id}/payments", response_model=S.PaymentResponse)
def create_payment(
    tenant_id: uuid.UUID,
    body: S.PaymentCreateRequest,
    ctx: RequestContext = Depends(require(P.PAYMENT_RECORD)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> S.PaymentResponse:
    match_tenant(ctx, tenant_id)
    payment = billing_payments.create_payment(
        db,
        tenant_id=tenant_id,
        actor_id=ctx.user_id,
        patient_id=body.patient_id,
        location_id=body.location_id,
        method=body.method,
        amount=body.amount,
        currency=body.currency,
        encounter_id=body.encounter_id,
        received_at=body.received_at,
        provider_ref=body.provider_ref,
        provider_data=body.provider_data,
        idempotency_key=idempotency_key or body.idempotency_key,
        location_ids=ctx.location_ids,
    )
    _payment_audit(db, ctx, action="payment.recorded", rid=str(payment.id))
    return _payment_resp(db, payment)


@router.get("/tenants/{tenant_id}/payments", response_model=S.PaymentListResponse)
def list_payments(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.BILLING_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    patient_id: uuid.UUID | None = None,
    status: str | None = None,
    limit: int = 50,
    cursor: uuid.UUID | None = None,
) -> S.PaymentListResponse:
    match_tenant(ctx, tenant_id)
    items, next_cursor = billing_payments.list_payments(
        db,
        tenant_id=tenant_id,
        patient_id=patient_id,
        status=status,
        location_ids=ctx.location_ids,
        limit=limit,
        cursor=cursor,
    )
    return S.PaymentListResponse(
        items=[_payment_resp(db, p) for p in items], next_cursor=next_cursor
    )


@router.get("/tenants/{tenant_id}/payments/{payment_id}", response_model=S.PaymentResponse)
def get_payment(
    tenant_id: uuid.UUID,
    payment_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.BILLING_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.PaymentResponse:
    match_tenant(ctx, tenant_id)
    return _payment_resp(
        db,
        billing_payments.get_payment(
            db, tenant_id=tenant_id, payment_id=payment_id, location_ids=ctx.location_ids
        ),
    )


@router.get(
    "/tenants/{tenant_id}/payments/{payment_id}/allocations",
    response_model=S.AllocationListResponse,
)
def list_payment_allocations(
    tenant_id: uuid.UUID,
    payment_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.BILLING_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.AllocationListResponse:
    match_tenant(ctx, tenant_id)
    payment = billing_payments.get_payment(
        db, tenant_id=tenant_id, payment_id=payment_id, location_ids=ctx.location_ids
    )
    return S.AllocationListResponse(
        items=[
            _allocation_resp(db, row)
            for row in billing_payments.payment_allocations(db, payment_id=payment.id)
        ]
    )


@router.post(
    "/tenants/{tenant_id}/payments/{payment_id}/allocations",
    response_model=S.AllocationListResponse,
)
def allocate_payment(
    tenant_id: uuid.UUID,
    payment_id: uuid.UUID,
    body: S.AllocateRequest,
    ctx: RequestContext = Depends(require(P.PAYMENT_RECORD)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> S.AllocationListResponse:
    match_tenant(ctx, tenant_id)
    payment, rows = billing_payments.allocate_payment(
        db,
        tenant_id=tenant_id,
        payment_id=payment_id,
        actor_id=ctx.user_id,
        items=[{"invoice_id": item.invoice_id, "amount": item.amount} for item in body.allocations],
        idempotency_key=idempotency_key or body.idempotency_key,
        location_ids=ctx.location_ids,
    )
    before = {row.invoice_id: None for row in rows}
    _payment_audit(db, ctx, action="payment.allocated", rid=str(payment.id))
    for invoice_id in before:
        invoice = billing_invoices.get_invoice(db, tenant_id=tenant_id, invoice_id=invoice_id)
        _invoice_audit(db, ctx, action=f"invoice.{invoice.status}", rid=str(invoice_id))
    return S.AllocationListResponse(items=[_allocation_resp(db, row) for row in rows])


@router.post(
    "/tenants/{tenant_id}/allocations/{allocation_id}/reverse",
    response_model=S.AllocationResponse,
)
def reverse_allocation(
    tenant_id: uuid.UUID,
    allocation_id: uuid.UUID,
    body: S.ReverseAllocationRequest,
    ctx: RequestContext = Depends(require(P.PAYMENT_RECORD)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.AllocationResponse:
    match_tenant(ctx, tenant_id)
    reversal = billing_payments.reverse_allocation(
        db,
        tenant_id=tenant_id,
        allocation_id=allocation_id,
        actor_id=ctx.user_id,
        reason=body.reason,
        location_ids=ctx.location_ids,
    )
    _allocation_audit(
        db, ctx, action="allocation.reversed", rid=str(reversal.id), reason=body.reason
    )
    return _allocation_resp(db, reversal)


@router.get(
    "/tenants/{tenant_id}/invoices/{invoice_id}/balance",
    response_model=S.InvoiceBalanceResponse,
)
def get_invoice_balance(
    tenant_id: uuid.UUID,
    invoice_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.BILLING_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.InvoiceBalanceResponse:
    match_tenant(ctx, tenant_id)
    invoice = billing_invoices.get_invoice(
        db, tenant_id=tenant_id, invoice_id=invoice_id, location_ids=ctx.location_ids
    )
    allocated = billing_invoices.effective_allocated(db, invoice_id=invoice.id)
    return S.InvoiceBalanceResponse(
        invoice_id=invoice.id,
        status=invoice.status,
        grand_total=str(invoice.grand_total),
        allocated_amount=str(allocated),
        outstanding_amount=str(billing_invoices.outstanding_for_invoice(db, invoice=invoice)),
    )


@router.get(
    "/tenants/{tenant_id}/patients/{patient_id}/credit-balance",
    response_model=S.PatientCreditResponse,
)
def get_patient_credit(
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.BILLING_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.PatientCreditResponse:
    match_tenant(ctx, tenant_id)
    return S.PatientCreditResponse(
        patient_id=patient_id,
        credit_amount=str(
            billing_payments.patient_credit(db, tenant_id=tenant_id, patient_id=patient_id)
        ),
    )


def _refund_audit(db: DBSession, ctx: RequestContext, *, action: str, rid: str) -> None:
    audit_service.append(
        db,
        tenant_id=ctx.tenant_id,
        actor_type="user",
        actor_id=str(ctx.user_id),
        action=action,
        resource_type="refund",
        resource_id=rid,
        request_id=request_id_ctx.get(),
    )


def _credit_audit(db: DBSession, ctx: RequestContext, *, action: str, rid: str) -> None:
    audit_service.append(
        db,
        tenant_id=ctx.tenant_id,
        actor_type="user",
        actor_id=str(ctx.user_id),
        action=action,
        resource_type="credit_note",
        resource_id=rid,
        request_id=request_id_ctx.get(),
    )


def _refund_resp(refund: Refund) -> S.RefundResponse:
    return S.RefundResponse(
        id=refund.id,
        payment_id=refund.payment_id,
        invoice_id=refund.invoice_id,
        status=refund.status,
        amount=str(refund.amount),
        currency=refund.currency,
        reason=refund.reason,
        created_at=refund.created_at,
        updated_at=refund.updated_at,
    )


def _credit_resp(note: CreditNote) -> S.CreditNoteResponse:
    return S.CreditNoteResponse(
        id=note.id,
        tenant_id=note.tenant_id,
        location_id=note.location_id,
        patient_id=note.patient_id,
        invoice_id=note.invoice_id,
        status=note.status,
        amount=str(note.amount),
        currency=note.currency,
        tax_rate=str(note.tax_rate),
        tax_amount=str(note.tax_amount),
        hsn_sac=note.hsn_sac,
        tax_treatment=note.tax_treatment,
        financial_year=note.financial_year,
        doc_number=note.doc_number,
        reason=note.reason,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


@router.post("/tenants/{tenant_id}/payments/{payment_id}/refunds", response_model=S.RefundResponse)
def create_refund(
    tenant_id: uuid.UUID,
    payment_id: uuid.UUID,
    body: S.RefundCreateRequest,
    ctx: RequestContext = Depends(require(P.BILLING_REFUND)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> S.RefundResponse:
    match_tenant(ctx, tenant_id)
    refund = billing_refunds.create_refund(
        db,
        tenant_id=tenant_id,
        payment_id=payment_id,
        actor_id=ctx.user_id,
        amount=body.amount,
        reason=body.reason,
        invoice_id=body.invoice_id,
        idempotency_key=idempotency_key or body.idempotency_key,
        location_ids=ctx.location_ids,
    )
    _refund_audit(db, ctx, action="refund.created", rid=str(refund.id))
    return _refund_resp(refund)


@router.get("/tenants/{tenant_id}/refunds/{refund_id}", response_model=S.RefundResponse)
def get_refund(
    tenant_id: uuid.UUID,
    refund_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.BILLING_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.RefundResponse:
    match_tenant(ctx, tenant_id)
    return _refund_resp(
        billing_refunds.get_refund(
            db, tenant_id=tenant_id, refund_id=refund_id, location_ids=ctx.location_ids
        )
    )


@router.get(
    "/tenants/{tenant_id}/payments/{payment_id}/refunds",
    response_model=S.RefundListResponse,
)
def list_payment_refunds(
    tenant_id: uuid.UUID,
    payment_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.BILLING_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.RefundListResponse:
    match_tenant(ctx, tenant_id)
    payment = billing_payments.get_payment(
        db, tenant_id=tenant_id, payment_id=payment_id, location_ids=ctx.location_ids
    )
    return S.RefundListResponse(
        items=[
            _refund_resp(row)
            for row in billing_refunds.refunds_for_payment(db, payment_id=payment.id)
        ]
    )


@router.post(
    "/tenants/{tenant_id}/invoices/{invoice_id}/credit-notes",
    response_model=S.CreditNoteResponse,
)
def create_credit_note(
    tenant_id: uuid.UUID,
    invoice_id: uuid.UUID,
    body: S.CreditNoteCreateRequest,
    ctx: RequestContext = Depends(require(P.BILLING_REFUND)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> S.CreditNoteResponse:
    match_tenant(ctx, tenant_id)
    note = billing_credit_notes.create_credit_note(
        db,
        tenant_id=tenant_id,
        invoice_id=invoice_id,
        actor_id=ctx.user_id,
        amount=body.amount,
        reason=body.reason,
        tax_rate=body.tax_rate if body.tax_rate is not None else 0,
        tax_amount=body.tax_amount if body.tax_amount is not None else 0,
        hsn_sac=body.hsn_sac,
        tax_treatment=body.tax_treatment,
        idempotency_key=idempotency_key or body.idempotency_key,
        location_ids=ctx.location_ids,
    )
    _credit_audit(db, ctx, action="credit_note.created", rid=str(note.id))
    return _credit_resp(note)


@router.post(
    "/tenants/{tenant_id}/credit-notes/{note_id}/issue",
    response_model=S.CreditNoteResponse,
)
def issue_credit_note(
    tenant_id: uuid.UUID,
    note_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.BILLING_REFUND)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.CreditNoteResponse:
    match_tenant(ctx, tenant_id)
    note = billing_credit_notes.issue_credit_note(
        db,
        tenant_id=tenant_id,
        note_id=note_id,
        actor_id=ctx.user_id,
        location_ids=ctx.location_ids,
    )
    _credit_audit(db, ctx, action="credit_note.issued", rid=str(note.id))
    return _credit_resp(note)


@router.post(
    "/tenants/{tenant_id}/credit-notes/{note_id}/void",
    response_model=S.CreditNoteResponse,
)
def void_credit_note(
    tenant_id: uuid.UUID,
    note_id: uuid.UUID,
    body: S.CreditNoteVoidRequest,
    ctx: RequestContext = Depends(require(P.BILLING_REFUND)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.CreditNoteResponse:
    match_tenant(ctx, tenant_id)
    note = billing_credit_notes.void_credit_note(
        db,
        tenant_id=tenant_id,
        note_id=note_id,
        actor_id=ctx.user_id,
        reason=body.reason,
        location_ids=ctx.location_ids,
    )
    _credit_audit(db, ctx, action="credit_note.voided", rid=str(note.id))
    return _credit_resp(note)


@router.get(
    "/tenants/{tenant_id}/credit-notes/{note_id}",
    response_model=S.CreditNoteResponse,
)
def get_credit_note(
    tenant_id: uuid.UUID,
    note_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.BILLING_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.CreditNoteResponse:
    match_tenant(ctx, tenant_id)
    return _credit_resp(
        billing_credit_notes.get_credit_note(
            db, tenant_id=tenant_id, note_id=note_id, location_ids=ctx.location_ids
        )
    )


@router.get(
    "/tenants/{tenant_id}/invoices/{invoice_id}/credit-notes",
    response_model=S.CreditNoteListResponse,
)
def list_invoice_credit_notes(
    tenant_id: uuid.UUID,
    invoice_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.BILLING_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.CreditNoteListResponse:
    match_tenant(ctx, tenant_id)
    invoice = billing_invoices.get_invoice(
        db, tenant_id=tenant_id, invoice_id=invoice_id, location_ids=ctx.location_ids
    )
    return S.CreditNoteListResponse(
        items=[
            _credit_resp(note)
            for note in billing_credit_notes.credit_notes_for_invoice(db, invoice_id=invoice.id)
        ]
    )


def _receipt_audit(db: DBSession, ctx: RequestContext, *, action: str, rid: str) -> None:
    audit_service.append(
        db,
        tenant_id=ctx.tenant_id,
        actor_type="user",
        actor_id=str(ctx.user_id),
        action=action,
        resource_type="receipt",
        resource_id=rid,
        request_id=request_id_ctx.get(),
    )


def _receipt_resp(receipt: Receipt) -> S.ReceiptResponse:
    return S.ReceiptResponse(
        id=receipt.id,
        tenant_id=receipt.tenant_id,
        location_id=receipt.location_id,
        patient_id=receipt.patient_id,
        payment_id=receipt.payment_id,
        amount=str(receipt.amount),
        currency=receipt.currency,
        financial_year=receipt.financial_year,
        doc_number=receipt.doc_number,
        created_at=receipt.created_at,
    )


@router.post(
    "/tenants/{tenant_id}/payments/{payment_id}/receipt",
    response_model=S.ReceiptResponse,
)
def create_receipt(
    tenant_id: uuid.UUID,
    payment_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.PAYMENT_RECORD)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    body: S.ReceiptCreateRequest | None = None,
) -> S.ReceiptResponse:
    match_tenant(ctx, tenant_id)
    receipt = billing_receipts.create_receipt(
        db,
        tenant_id=tenant_id,
        payment_id=payment_id,
        actor_id=ctx.user_id,
        idempotency_key=idempotency_key or (body.idempotency_key if body else None),
        location_ids=ctx.location_ids,
    )
    _receipt_audit(db, ctx, action="receipt.issued", rid=str(receipt.id))
    return _receipt_resp(receipt)


@router.get(
    "/tenants/{tenant_id}/receipts/{receipt_id}",
    response_model=S.ReceiptResponse,
)
def get_receipt(
    tenant_id: uuid.UUID,
    receipt_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.BILLING_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.ReceiptResponse:
    match_tenant(ctx, tenant_id)
    return _receipt_resp(
        billing_receipts.get_receipt(
            db, tenant_id=tenant_id, receipt_id=receipt_id, location_ids=ctx.location_ids
        )
    )
