"""Inventory API: items, suppliers, ledger movements, purchase receipts."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DBSession

from app.api.deps import get_db, require
from app.api.v1._shared import match_tenant
from app.modules.audit import service as audit_service
from app.modules.inventory import schemas as S
from app.modules.inventory import service as inv
from app.modules.inventory.models import (
    GoodsReceipt,
    InventoryItem,
    InventoryMovement,
    InventorySupplier,
    PurchaseOrder,
)
from app.platform.authz.permissions import P
from app.platform.authz.scope import RequestContext
from app.platform.request_context import request_id_ctx

router = APIRouter(tags=["inventory"])


def _audit(
    db: DBSession, ctx: RequestContext, *, action: str, rtype: str, rid: str
) -> None:
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


def _item(row: InventoryItem) -> S.ItemResponse:
    return S.ItemResponse(
        id=row.id,
        sku=row.sku,
        name=row.name,
        category=row.category,
        description=row.description,
        unit=row.unit,
        cost_price=str(row.cost_price),
        reorder_level=str(row.reorder_level),
        is_active=row.is_active,
    )


def _supplier(row: InventorySupplier) -> S.SupplierResponse:
    return S.SupplierResponse(
        id=row.id,
        name=row.name,
        contact_name=row.contact_name,
        phone=row.phone,
        email=row.email,
        address=row.address,
        tax_id=row.tax_id,
        is_active=row.is_active,
    )


def _movement(row: InventoryMovement) -> S.MovementResponse:
    return S.MovementResponse(
        id=row.id,
        location_id=row.location_id,
        item_id=row.item_id,
        kind=row.kind,
        quantity_delta=str(row.quantity_delta),
        unit_cost=None if row.unit_cost is None else str(row.unit_cost),
        reason=row.reason,
        reference_type=row.reference_type,
        reference_id=row.reference_id,
        occurred_at=row.occurred_at,
    )


def _po(db: DBSession, po: PurchaseOrder) -> S.PurchaseOrderResponse:
    lines = [
        S.PurchaseOrderLineResponse(
            id=ln.id,
            item_id=ln.item_id,
            quantity_ordered=str(ln.quantity_ordered),
            quantity_received=str(ln.quantity_received),
            unit_cost=str(ln.unit_cost),
            line_no=ln.line_no,
        )
        for ln in inv.po_lines(db, purchase_order_id=po.id)
    ]
    return S.PurchaseOrderResponse(
        id=po.id,
        location_id=po.location_id,
        supplier_id=po.supplier_id,
        status=po.status,
        notes=po.notes,
        ordered_at=po.ordered_at,
        created_at=po.created_at,
        lines=lines,
    )


def _gr(row: GoodsReceipt) -> S.GoodsReceiptResponse:
    return S.GoodsReceiptResponse(
        id=row.id,
        purchase_order_id=row.purchase_order_id,
        location_id=row.location_id,
        status=row.status,
        receipt_key=row.receipt_key,
        received_at=row.received_at,
    )


# --- Items ---


@router.post("/tenants/{tenant_id}/inventory/items", response_model=S.ItemResponse)
def create_item(
    tenant_id: uuid.UUID,
    body: S.ItemCreateRequest,
    ctx: RequestContext = Depends(require(P.INVENTORY_MANAGE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.ItemResponse:
    match_tenant(ctx, tenant_id)
    row = inv.create_item(
        db,
        tenant_id=tenant_id,
        sku=body.sku,
        name=body.name,
        category=body.category,
        description=body.description,
        unit=body.unit,
        cost_price=body.cost_price,
        reorder_level=body.reorder_level,
    )
    _audit(db, ctx, action="inventory.item.created", rtype="inventory_item", rid=str(row.id))
    return _item(row)


@router.get("/tenants/{tenant_id}/inventory/items", response_model=list[S.ItemResponse])
def list_items(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.INVENTORY_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    q: str | None = None,
    category: str | None = None,
    active_only: bool = False,
    limit: int = 100,
) -> list[S.ItemResponse]:
    match_tenant(ctx, tenant_id)
    return [
        _item(r)
        for r in inv.list_items(
            db,
            tenant_id=tenant_id,
            q=q,
            category=category,
            active_only=active_only,
            limit=limit,
        )
    ]


@router.get("/tenants/{tenant_id}/inventory/items/{item_id}", response_model=S.ItemResponse)
def get_item(
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.INVENTORY_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.ItemResponse:
    match_tenant(ctx, tenant_id)
    return _item(inv.get_item(db, tenant_id=tenant_id, item_id=item_id))


@router.patch("/tenants/{tenant_id}/inventory/items/{item_id}", response_model=S.ItemResponse)
def patch_item(
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    body: S.ItemUpdateRequest,
    ctx: RequestContext = Depends(require(P.INVENTORY_MANAGE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.ItemResponse:
    match_tenant(ctx, tenant_id)
    row = inv.update_item(
        db, tenant_id=tenant_id, item_id=item_id, fields=body.model_dump(exclude_unset=True)
    )
    _audit(db, ctx, action="inventory.item.updated", rtype="inventory_item", rid=str(row.id))
    return _item(row)


# --- Suppliers ---


@router.post("/tenants/{tenant_id}/inventory/suppliers", response_model=S.SupplierResponse)
def create_supplier(
    tenant_id: uuid.UUID,
    body: S.SupplierCreateRequest,
    ctx: RequestContext = Depends(require(P.INVENTORY_MANAGE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.SupplierResponse:
    match_tenant(ctx, tenant_id)
    row = inv.create_supplier(
        db,
        tenant_id=tenant_id,
        name=body.name,
        contact_name=body.contact_name,
        phone=body.phone,
        email=body.email,
        address=body.address,
        tax_id=body.tax_id,
    )
    _audit(
        db,
        ctx,
        action="inventory.supplier.created",
        rtype="inventory_supplier",
        rid=str(row.id),
    )
    return _supplier(row)


@router.get("/tenants/{tenant_id}/inventory/suppliers", response_model=list[S.SupplierResponse])
def list_suppliers(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.INVENTORY_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    active_only: bool = False,
) -> list[S.SupplierResponse]:
    match_tenant(ctx, tenant_id)
    return [
        _supplier(r)
        for r in inv.list_suppliers(db, tenant_id=tenant_id, active_only=active_only)
    ]


# --- Stock ---


@router.get("/tenants/{tenant_id}/inventory/balances", response_model=list[S.BalanceResponse])
def list_balances(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.INVENTORY_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    location_id: uuid.UUID | None = None,
    low_stock_only: bool = False,
) -> list[S.BalanceResponse]:
    match_tenant(ctx, tenant_id)
    rows = inv.list_balances(
        db,
        tenant_id=tenant_id,
        location_id=location_id,
        location_ids=ctx.location_ids or None,
        low_stock_only=low_stock_only,
    )
    return [
        S.BalanceResponse(
            item_id=i.id,
            location_id=b.location_id,
            sku=i.sku,
            name=i.name,
            unit=i.unit,
            quantity_on_hand=str(b.quantity_on_hand),
            reorder_level=str(i.reorder_level),
            cost_price=str(i.cost_price),
            is_low=b.quantity_on_hand <= i.reorder_level,
        )
        for b, i in rows
    ]


@router.get("/tenants/{tenant_id}/inventory/movements", response_model=list[S.MovementResponse])
def list_movements(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.INVENTORY_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    location_id: uuid.UUID | None = None,
    item_id: uuid.UUID | None = None,
    limit: int = 50,
) -> list[S.MovementResponse]:
    match_tenant(ctx, tenant_id)
    return [
        _movement(m)
        for m in inv.list_movements(
            db,
            tenant_id=tenant_id,
            location_id=location_id,
            item_id=item_id,
            location_ids=ctx.location_ids or None,
            limit=limit,
        )
    ]


@router.post("/tenants/{tenant_id}/inventory/opening-stock", response_model=S.MovementResponse)
def opening_stock(
    tenant_id: uuid.UUID,
    body: S.OpeningStockRequest,
    ctx: RequestContext = Depends(require(P.INVENTORY_ADJUST)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.MovementResponse:
    match_tenant(ctx, tenant_id)
    mv = inv.post_opening_stock(
        db,
        tenant_id=tenant_id,
        actor_id=ctx.user_id,
        location_id=body.location_id,
        item_id=body.item_id,
        quantity=body.quantity,
        unit_cost=body.unit_cost,
        location_ids=ctx.location_ids or None,
        idempotency_key=body.idempotency_key,
    )
    _audit(db, ctx, action="inventory.opening", rtype="inventory_movement", rid=str(mv.id))
    return _movement(mv)


@router.post("/tenants/{tenant_id}/inventory/adjustments", response_model=S.MovementResponse)
def adjust_stock(
    tenant_id: uuid.UUID,
    body: S.AdjustStockRequest,
    ctx: RequestContext = Depends(require(P.INVENTORY_ADJUST)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.MovementResponse:
    match_tenant(ctx, tenant_id)
    mv = inv.adjust_stock(
        db,
        tenant_id=tenant_id,
        actor_id=ctx.user_id,
        location_id=body.location_id,
        item_id=body.item_id,
        quantity_delta=body.quantity_delta,
        reason=body.reason,
        location_ids=ctx.location_ids or None,
        idempotency_key=body.idempotency_key,
    )
    _audit(db, ctx, action="inventory.adjusted", rtype="inventory_movement", rid=str(mv.id))
    return _movement(mv)


@router.post("/tenants/{tenant_id}/inventory/consume", response_model=S.MovementResponse)
def consume_stock(
    tenant_id: uuid.UUID,
    body: S.ConsumeStockRequest,
    ctx: RequestContext = Depends(require(P.INVENTORY_ADJUST)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.MovementResponse:
    match_tenant(ctx, tenant_id)
    mv = inv.consume_stock(
        db,
        tenant_id=tenant_id,
        actor_id=ctx.user_id,
        location_id=body.location_id,
        item_id=body.item_id,
        quantity=body.quantity,
        reason=body.reason,
        reference_type=body.reference_type,
        reference_id=body.reference_id,
        location_ids=ctx.location_ids or None,
        idempotency_key=body.idempotency_key,
    )
    _audit(db, ctx, action="inventory.consumed", rtype="inventory_movement", rid=str(mv.id))
    return _movement(mv)


@router.post("/tenants/{tenant_id}/inventory/wastage", response_model=S.MovementResponse)
def wastage(
    tenant_id: uuid.UUID,
    body: S.WastageRequest,
    ctx: RequestContext = Depends(require(P.INVENTORY_ADJUST)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.MovementResponse:
    match_tenant(ctx, tenant_id)
    mv = inv.record_wastage(
        db,
        tenant_id=tenant_id,
        actor_id=ctx.user_id,
        location_id=body.location_id,
        item_id=body.item_id,
        quantity=body.quantity,
        reason=body.reason,
        location_ids=ctx.location_ids or None,
        idempotency_key=body.idempotency_key,
    )
    _audit(db, ctx, action="inventory.wastage", rtype="inventory_movement", rid=str(mv.id))
    return _movement(mv)


@router.post("/tenants/{tenant_id}/inventory/returns", response_model=S.MovementResponse)
def return_stock(
    tenant_id: uuid.UUID,
    body: S.ReturnStockRequest,
    ctx: RequestContext = Depends(require(P.INVENTORY_ADJUST)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.MovementResponse:
    match_tenant(ctx, tenant_id)
    mv = inv.return_to_stock(
        db,
        tenant_id=tenant_id,
        actor_id=ctx.user_id,
        location_id=body.location_id,
        item_id=body.item_id,
        quantity=body.quantity,
        reason=body.reason,
        location_ids=ctx.location_ids or None,
        idempotency_key=body.idempotency_key,
    )
    _audit(db, ctx, action="inventory.returned", rtype="inventory_movement", rid=str(mv.id))
    return _movement(mv)


@router.post("/tenants/{tenant_id}/inventory/transfers", response_model=list[S.MovementResponse])
def transfer_stock(
    tenant_id: uuid.UUID,
    body: S.TransferStockRequest,
    ctx: RequestContext = Depends(require(P.INVENTORY_ADJUST)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> list[S.MovementResponse]:
    match_tenant(ctx, tenant_id)
    out_mv, in_mv = inv.transfer_stock(
        db,
        tenant_id=tenant_id,
        actor_id=ctx.user_id,
        from_location_id=body.from_location_id,
        to_location_id=body.to_location_id,
        item_id=body.item_id,
        quantity=body.quantity,
        location_ids=ctx.location_ids or None,
        idempotency_key=body.idempotency_key,
    )
    _audit(db, ctx, action="inventory.transferred", rtype="inventory_movement", rid=str(out_mv.id))
    return [_movement(out_mv), _movement(in_mv)]


# --- Purchase ---


@router.post(
    "/tenants/{tenant_id}/inventory/purchase-orders", response_model=S.PurchaseOrderResponse
)
def create_po(
    tenant_id: uuid.UUID,
    body: S.PurchaseOrderCreateRequest,
    ctx: RequestContext = Depends(require(P.INVENTORY_PURCHASE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.PurchaseOrderResponse:
    match_tenant(ctx, tenant_id)
    po = inv.create_purchase_order(
        db,
        tenant_id=tenant_id,
        actor_id=ctx.user_id,
        location_id=body.location_id,
        supplier_id=body.supplier_id,
        lines=[ln.model_dump() for ln in body.lines],
        notes=body.notes,
        location_ids=ctx.location_ids or None,
    )
    _audit(db, ctx, action="inventory.po.created", rtype="purchase_order", rid=str(po.id))
    return _po(db, po)


@router.get(
    "/tenants/{tenant_id}/inventory/purchase-orders", response_model=list[S.PurchaseOrderResponse]
)
def list_pos(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.INVENTORY_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    location_id: uuid.UUID | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[S.PurchaseOrderResponse]:
    match_tenant(ctx, tenant_id)
    return [
        _po(db, po)
        for po in inv.list_purchase_orders(
            db,
            tenant_id=tenant_id,
            location_id=location_id,
            status=status,
            location_ids=ctx.location_ids or None,
            limit=limit,
        )
    ]


@router.get(
    "/tenants/{tenant_id}/inventory/purchase-orders/{purchase_order_id}",
    response_model=S.PurchaseOrderResponse,
)
def get_po(
    tenant_id: uuid.UUID,
    purchase_order_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.INVENTORY_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.PurchaseOrderResponse:
    match_tenant(ctx, tenant_id)
    po = inv.get_purchase_order(
        db,
        tenant_id=tenant_id,
        purchase_order_id=purchase_order_id,
        location_ids=ctx.location_ids or None,
    )
    return _po(db, po)


@router.post(
    "/tenants/{tenant_id}/inventory/purchase-orders/{purchase_order_id}/submit",
    response_model=S.PurchaseOrderResponse,
)
def submit_po(
    tenant_id: uuid.UUID,
    purchase_order_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.INVENTORY_PURCHASE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.PurchaseOrderResponse:
    match_tenant(ctx, tenant_id)
    po = inv.submit_purchase_order(
        db,
        tenant_id=tenant_id,
        purchase_order_id=purchase_order_id,
        location_ids=ctx.location_ids or None,
    )
    _audit(db, ctx, action="inventory.po.submitted", rtype="purchase_order", rid=str(po.id))
    return _po(db, po)


@router.post(
    "/tenants/{tenant_id}/inventory/purchase-orders/{purchase_order_id}/cancel",
    response_model=S.PurchaseOrderResponse,
)
def cancel_po(
    tenant_id: uuid.UUID,
    purchase_order_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.INVENTORY_PURCHASE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.PurchaseOrderResponse:
    match_tenant(ctx, tenant_id)
    po = inv.cancel_purchase_order(
        db,
        tenant_id=tenant_id,
        purchase_order_id=purchase_order_id,
        location_ids=ctx.location_ids or None,
    )
    _audit(db, ctx, action="inventory.po.cancelled", rtype="purchase_order", rid=str(po.id))
    return _po(db, po)


@router.post(
    "/tenants/{tenant_id}/inventory/purchase-orders/{purchase_order_id}/receive",
    response_model=S.GoodsReceiptResponse,
)
def receive_po(
    tenant_id: uuid.UUID,
    purchase_order_id: uuid.UUID,
    body: S.GoodsReceiptRequest,
    ctx: RequestContext = Depends(require(P.INVENTORY_PURCHASE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.GoodsReceiptResponse:
    match_tenant(ctx, tenant_id)
    gr = inv.receive_goods(
        db,
        tenant_id=tenant_id,
        actor_id=ctx.user_id,
        purchase_order_id=purchase_order_id,
        receipt_key=body.receipt_key,
        lines=[ln.model_dump() for ln in body.lines],
        location_ids=ctx.location_ids or None,
    )
    _audit(db, ctx, action="inventory.goods_received", rtype="goods_receipt", rid=str(gr.id))
    return _gr(gr)


@router.get("/tenants/{tenant_id}/inventory/dashboard", response_model=S.DashboardResponse)
def dashboard(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.INVENTORY_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    location_id: uuid.UUID | None = None,
) -> S.DashboardResponse:
    match_tenant(ctx, tenant_id)
    summary = inv.dashboard_summary(
        db,
        tenant_id=tenant_id,
        location_id=location_id,
        location_ids=ctx.location_ids or None,
    )
    return S.DashboardResponse(
        active_items=summary["active_items"],
        low_stock_count=summary["low_stock_count"],
        out_of_stock_count=summary["out_of_stock_count"],
        stock_valuation=summary["stock_valuation"],
        recent_movements=[_movement(m) for m in summary["recent_movements"]],
        recent_purchase_orders=[_po(db, po) for po in summary["recent_purchase_orders"]],
    )
