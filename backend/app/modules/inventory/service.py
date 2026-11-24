"""Inventory services: catalog, suppliers, ledger, purchase receipts.

Stock invariants:
- Balances change only via `_apply_delta` with SELECT FOR UPDATE.
- Movements are append-only.
- Quantity on hand never goes negative.
- Goods receipts are idempotent on (tenant, receipt_key).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TypedDict

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.modules.clinics import service as clinics_service
from app.modules.inventory import models as M
from app.modules.inventory.models import (
    GoodsReceipt,
    GoodsReceiptLine,
    InventoryBalance,
    InventoryItem,
    InventoryMovement,
    InventorySupplier,
    PurchaseOrder,
    PurchaseOrderLine,
)
from app.platform import ids
from app.platform.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.platform.time import now

QTY = Decimal("0.0001")
MONEY = Decimal("0.01")


def _dec(value: object, *, field: str, min_value: Decimal | None = None) -> Decimal:
    try:
        d = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:
        raise ValidationError(f"invalid {field}") from exc
    if min_value is not None and d < min_value:
        raise ValidationError(f"{field} must be >= {min_value}")
    return d


def _check_location(
    location_ids: frozenset[uuid.UUID] | None, location_id: uuid.UUID
) -> None:
    if location_ids and location_id not in location_ids:
        raise ForbiddenError("location is outside your scope")


def _norm_sku(sku: str) -> str:
    cleaned = (sku or "").strip().upper()
    if len(cleaned) < 1 or len(cleaned) > 64:
        raise ValidationError("sku must be 1-64 characters")
    return cleaned


# --- Items ---


def create_item(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    sku: str,
    name: str,
    category: str = "general",
    description: str | None = None,
    unit: str = "each",
    cost_price: object = "0",
    reorder_level: object = "0",
) -> InventoryItem:
    from app.modules.subscriptions.commercial_policy import assert_feature

    assert_feature(
        db, tenant_id=tenant_id, feature_key="inventory", operation="inventory.item.create"
    )
    code = _norm_sku(sku)
    cleaned_name = (name or "").strip()
    if len(cleaned_name) < 2 or len(cleaned_name) > 200:
        raise ValidationError("name must be 2-200 characters")
    existing = db.execute(
        select(InventoryItem).where(
            InventoryItem.tenant_id == tenant_id, InventoryItem.sku == code
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("item with this SKU already exists")
    ts = now()
    row = InventoryItem(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        sku=code,
        name=cleaned_name,
        category=(category or "general").strip()[:80] or "general",
        description=(description or "").strip() or None,
        unit=(unit or "each").strip()[:32] or "each",
        cost_price=_dec(cost_price, field="cost_price", min_value=Decimal("0")),
        reorder_level=_dec(reorder_level, field="reorder_level", min_value=Decimal("0")),
        is_active=True,
        created_at=ts,
        updated_at=ts,
    )
    db.add(row)
    db.flush()
    return row


def get_item(db: DBSession, *, tenant_id: uuid.UUID, item_id: uuid.UUID) -> InventoryItem:
    row = db.get(InventoryItem, item_id)
    if row is None or row.tenant_id != tenant_id:
        raise NotFoundError("item not found")
    return row


def list_items(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    q: str | None = None,
    category: str | None = None,
    active_only: bool = False,
    limit: int = 100,
) -> list[InventoryItem]:
    stmt = select(InventoryItem).where(InventoryItem.tenant_id == tenant_id)
    if active_only:
        stmt = stmt.where(InventoryItem.is_active.is_(True))
    if category:
        stmt = stmt.where(InventoryItem.category == category)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            (InventoryItem.name.ilike(like)) | (InventoryItem.sku.ilike(like))
        )
    return list(
        db.execute(stmt.order_by(InventoryItem.name).limit(min(max(limit, 1), 200)))
        .scalars()
        .all()
    )


def update_item(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    fields: dict[str, object],
) -> InventoryItem:
    row = get_item(db, tenant_id=tenant_id, item_id=item_id)
    if "name" in fields and fields["name"] is not None:
        name = str(fields["name"]).strip()
        if len(name) < 2:
            raise ValidationError("name must be 2-200 characters")
        row.name = name
    if "category" in fields and fields["category"] is not None:
        row.category = str(fields["category"]).strip()[:80] or "general"
    if "description" in fields:
        desc = fields["description"]
        row.description = None if desc is None else str(desc).strip() or None
    if "unit" in fields and fields["unit"] is not None:
        row.unit = str(fields["unit"]).strip()[:32] or "each"
    if "cost_price" in fields and fields["cost_price"] is not None:
        row.cost_price = _dec(fields["cost_price"], field="cost_price", min_value=Decimal("0"))
    if "reorder_level" in fields and fields["reorder_level"] is not None:
        row.reorder_level = _dec(
            fields["reorder_level"], field="reorder_level", min_value=Decimal("0")
        )
    if "is_active" in fields and fields["is_active"] is not None:
        row.is_active = bool(fields["is_active"])
    row.updated_at = now()
    db.flush()
    return row


# --- Suppliers ---


def create_supplier(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    name: str,
    contact_name: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    address: str | None = None,
    tax_id: str | None = None,
) -> InventorySupplier:
    from app.modules.subscriptions.commercial_policy import assert_feature

    assert_feature(
        db, tenant_id=tenant_id, feature_key="inventory", operation="inventory.supplier.create"
    )
    cleaned = (name or "").strip()
    if len(cleaned) < 2:
        raise ValidationError("supplier name must be 2-200 characters")
    dup = db.execute(
        select(InventorySupplier).where(
            InventorySupplier.tenant_id == tenant_id,
            InventorySupplier.name == cleaned,
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise ConflictError("supplier with this name already exists")
    ts = now()
    row = InventorySupplier(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        name=cleaned,
        contact_name=(contact_name or "").strip() or None,
        phone=(phone or "").strip() or None,
        email=(email or "").strip() or None,
        address=(address or "").strip() or None,
        tax_id=(tax_id or "").strip() or None,
        is_active=True,
        created_at=ts,
        updated_at=ts,
    )
    db.add(row)
    db.flush()
    return row


def get_supplier(
    db: DBSession, *, tenant_id: uuid.UUID, supplier_id: uuid.UUID
) -> InventorySupplier:
    row = db.get(InventorySupplier, supplier_id)
    if row is None or row.tenant_id != tenant_id:
        raise NotFoundError("supplier not found")
    return row


def list_suppliers(
    db: DBSession, *, tenant_id: uuid.UUID, active_only: bool = False, limit: int = 100
) -> list[InventorySupplier]:
    stmt = select(InventorySupplier).where(InventorySupplier.tenant_id == tenant_id)
    if active_only:
        stmt = stmt.where(InventorySupplier.is_active.is_(True))
    return list(
        db.execute(stmt.order_by(InventorySupplier.name).limit(min(max(limit, 1), 200)))
        .scalars()
        .all()
    )


# --- Ledger / balances ---


def _lock_balance(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID,
    item_id: uuid.UUID,
) -> InventoryBalance:
    row = db.execute(
        select(InventoryBalance)
        .where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.location_id == location_id,
            InventoryBalance.item_id == item_id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if row is not None:
        return row
    # Create then re-lock to serialize concurrent first writers.
    ts = now()
    row = InventoryBalance(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        location_id=location_id,
        item_id=item_id,
        quantity_on_hand=Decimal("0"),
        updated_at=ts,
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        existing = db.execute(
            select(InventoryBalance)
            .where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.location_id == location_id,
                InventoryBalance.item_id == item_id,
            )
            .with_for_update()
        ).scalar_one()
        return existing
    locked = db.execute(
        select(InventoryBalance)
        .where(InventoryBalance.id == row.id)
        .with_for_update()
    ).scalar_one()
    return locked


def _apply_delta(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID,
    item_id: uuid.UUID,
    kind: str,
    quantity_delta: Decimal,
    actor_id: uuid.UUID | None,
    unit_cost: Decimal | None = None,
    reason: str | None = None,
    reference_type: str | None = None,
    reference_id: uuid.UUID | None = None,
    transfer_group_id: uuid.UUID | None = None,
    idempotency_key: str | None = None,
) -> InventoryMovement:
    if kind not in M.MOVEMENT_KINDS:
        raise ValidationError("unknown movement kind")
    if quantity_delta == 0:
        raise ValidationError("quantity_delta must be non-zero")

    if idempotency_key:
        existing = db.execute(
            select(InventoryMovement).where(
                InventoryMovement.tenant_id == tenant_id,
                InventoryMovement.idempotency_key == idempotency_key,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

    bal = _lock_balance(
        db, tenant_id=tenant_id, location_id=location_id, item_id=item_id
    )
    new_qty = bal.quantity_on_hand + quantity_delta
    if new_qty < 0:
        raise ConflictError("insufficient stock")
    bal.quantity_on_hand = new_qty
    bal.updated_at = now()
    ts = now()
    mv = InventoryMovement(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        location_id=location_id,
        item_id=item_id,
        kind=kind,
        quantity_delta=quantity_delta,
        unit_cost=unit_cost,
        reason=(reason or "").strip() or None,
        reference_type=reference_type,
        reference_id=reference_id,
        transfer_group_id=transfer_group_id,
        recorded_by=actor_id,
        occurred_at=ts,
        created_at=ts,
        idempotency_key=idempotency_key,
    )
    db.add(mv)
    db.flush()
    return mv


def post_opening_stock(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    location_id: uuid.UUID,
    item_id: uuid.UUID,
    quantity: object,
    unit_cost: object | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
    idempotency_key: str | None = None,
) -> InventoryMovement:
    clinics_service.get_location(db, tenant_id=tenant_id, location_id=location_id)
    _check_location(location_ids, location_id)
    get_item(db, tenant_id=tenant_id, item_id=item_id)
    qty = _dec(quantity, field="quantity", min_value=QTY)
    cost = (
        None
        if unit_cost is None
        else _dec(unit_cost, field="unit_cost", min_value=Decimal("0"))
    )
    return _apply_delta(
        db,
        tenant_id=tenant_id,
        location_id=location_id,
        item_id=item_id,
        kind=M.MV_OPENING,
        quantity_delta=qty,
        actor_id=actor_id,
        unit_cost=cost,
        reason="opening stock",
        idempotency_key=idempotency_key,
    )


def adjust_stock(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    location_id: uuid.UUID,
    item_id: uuid.UUID,
    quantity_delta: object,
    reason: str,
    location_ids: frozenset[uuid.UUID] | None = None,
    idempotency_key: str | None = None,
) -> InventoryMovement:
    from app.modules.subscriptions.commercial_policy import assert_feature

    assert_feature(
        db, tenant_id=tenant_id, feature_key="inventory", operation="inventory.adjust"
    )
    clinics_service.get_location(db, tenant_id=tenant_id, location_id=location_id)
    _check_location(location_ids, location_id)
    get_item(db, tenant_id=tenant_id, item_id=item_id)
    delta = _dec(quantity_delta, field="quantity_delta")
    if delta == 0:
        raise ValidationError("quantity_delta must be non-zero")
    cleaned = (reason or "").strip()
    if len(cleaned) < 2:
        raise ValidationError("reason required")
    return _apply_delta(
        db,
        tenant_id=tenant_id,
        location_id=location_id,
        item_id=item_id,
        kind=M.MV_ADJUSTMENT,
        quantity_delta=delta,
        actor_id=actor_id,
        reason=cleaned,
        idempotency_key=idempotency_key,
    )


def consume_stock(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    location_id: uuid.UUID,
    item_id: uuid.UUID,
    quantity: object,
    reason: str,
    reference_type: str | None = None,
    reference_id: uuid.UUID | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
    idempotency_key: str | None = None,
) -> InventoryMovement:
    clinics_service.get_location(db, tenant_id=tenant_id, location_id=location_id)
    _check_location(location_ids, location_id)
    get_item(db, tenant_id=tenant_id, item_id=item_id)
    qty = _dec(quantity, field="quantity", min_value=QTY)
    cleaned = (reason or "").strip()
    if len(cleaned) < 2:
        raise ValidationError("reason required")
    return _apply_delta(
        db,
        tenant_id=tenant_id,
        location_id=location_id,
        item_id=item_id,
        kind=M.MV_CONSUMPTION,
        quantity_delta=-qty,
        actor_id=actor_id,
        reason=cleaned,
        reference_type=reference_type,
        reference_id=reference_id,
        idempotency_key=idempotency_key,
    )


def record_wastage(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    location_id: uuid.UUID,
    item_id: uuid.UUID,
    quantity: object,
    reason: str,
    location_ids: frozenset[uuid.UUID] | None = None,
    idempotency_key: str | None = None,
) -> InventoryMovement:
    clinics_service.get_location(db, tenant_id=tenant_id, location_id=location_id)
    _check_location(location_ids, location_id)
    get_item(db, tenant_id=tenant_id, item_id=item_id)
    qty = _dec(quantity, field="quantity", min_value=QTY)
    cleaned = (reason or "").strip()
    if len(cleaned) < 2:
        raise ValidationError("reason required")
    return _apply_delta(
        db,
        tenant_id=tenant_id,
        location_id=location_id,
        item_id=item_id,
        kind=M.MV_WASTAGE,
        quantity_delta=-qty,
        actor_id=actor_id,
        reason=cleaned,
        idempotency_key=idempotency_key,
    )


def return_to_stock(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    location_id: uuid.UUID,
    item_id: uuid.UUID,
    quantity: object,
    reason: str,
    location_ids: frozenset[uuid.UUID] | None = None,
    idempotency_key: str | None = None,
) -> InventoryMovement:
    clinics_service.get_location(db, tenant_id=tenant_id, location_id=location_id)
    _check_location(location_ids, location_id)
    get_item(db, tenant_id=tenant_id, item_id=item_id)
    qty = _dec(quantity, field="quantity", min_value=QTY)
    cleaned = (reason or "").strip()
    if len(cleaned) < 2:
        raise ValidationError("reason required")
    return _apply_delta(
        db,
        tenant_id=tenant_id,
        location_id=location_id,
        item_id=item_id,
        kind=M.MV_RETURN,
        quantity_delta=qty,
        actor_id=actor_id,
        reason=cleaned,
        idempotency_key=idempotency_key,
    )


def transfer_stock(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    from_location_id: uuid.UUID,
    to_location_id: uuid.UUID,
    item_id: uuid.UUID,
    quantity: object,
    location_ids: frozenset[uuid.UUID] | None = None,
    idempotency_key: str | None = None,
) -> tuple[InventoryMovement, InventoryMovement]:
    if from_location_id == to_location_id:
        raise ValidationError("transfer locations must differ")
    clinics_service.get_location(db, tenant_id=tenant_id, location_id=from_location_id)
    clinics_service.get_location(db, tenant_id=tenant_id, location_id=to_location_id)
    _check_location(location_ids, from_location_id)
    _check_location(location_ids, to_location_id)
    get_item(db, tenant_id=tenant_id, item_id=item_id)
    qty = _dec(quantity, field="quantity", min_value=QTY)
    group = ids.uuid7()
    # Lock both balances in deterministic order to avoid deadlocks.
    loc_a, loc_b = sorted([from_location_id, to_location_id], key=str)
    _lock_balance(db, tenant_id=tenant_id, location_id=loc_a, item_id=item_id)
    _lock_balance(db, tenant_id=tenant_id, location_id=loc_b, item_id=item_id)
    out_key = f"{idempotency_key}:out" if idempotency_key else None
    in_key = f"{idempotency_key}:in" if idempotency_key else None
    mv_out = _apply_delta(
        db,
        tenant_id=tenant_id,
        location_id=from_location_id,
        item_id=item_id,
        kind=M.MV_TRANSFER_OUT,
        quantity_delta=-qty,
        actor_id=actor_id,
        reason="location transfer",
        transfer_group_id=group,
        idempotency_key=out_key,
    )
    mv_in = _apply_delta(
        db,
        tenant_id=tenant_id,
        location_id=to_location_id,
        item_id=item_id,
        kind=M.MV_TRANSFER_IN,
        quantity_delta=qty,
        actor_id=actor_id,
        reason="location transfer",
        transfer_group_id=group,
        idempotency_key=in_key,
    )
    return mv_out, mv_in


def get_balance(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID,
    item_id: uuid.UUID,
) -> Decimal:
    row = db.execute(
        select(InventoryBalance).where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.location_id == location_id,
            InventoryBalance.item_id == item_id,
        )
    ).scalar_one_or_none()
    return row.quantity_on_hand if row else Decimal("0")


def list_balances(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
    low_stock_only: bool = False,
    limit: int = 200,
) -> list[tuple[InventoryBalance, InventoryItem]]:
    stmt = (
        select(InventoryBalance, InventoryItem)
        .join(InventoryItem, InventoryItem.id == InventoryBalance.item_id)
        .where(InventoryBalance.tenant_id == tenant_id)
    )
    if location_id is not None:
        _check_location(location_ids, location_id)
        stmt = stmt.where(InventoryBalance.location_id == location_id)
    elif location_ids:
        stmt = stmt.where(InventoryBalance.location_id.in_(list(location_ids)))
    if low_stock_only:
        stmt = stmt.where(
            InventoryBalance.quantity_on_hand <= InventoryItem.reorder_level
        )
    rows = db.execute(
        stmt.order_by(InventoryItem.name).limit(min(max(limit, 1), 500))
    ).all()
    return [(b, i) for b, i in rows]


def list_movements(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID | None = None,
    item_id: uuid.UUID | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
    limit: int = 50,
) -> list[InventoryMovement]:
    stmt = select(InventoryMovement).where(InventoryMovement.tenant_id == tenant_id)
    if location_id is not None:
        _check_location(location_ids, location_id)
        stmt = stmt.where(InventoryMovement.location_id == location_id)
    elif location_ids:
        stmt = stmt.where(InventoryMovement.location_id.in_(list(location_ids)))
    if item_id is not None:
        stmt = stmt.where(InventoryMovement.item_id == item_id)
    return list(
        db.execute(
            stmt.order_by(InventoryMovement.occurred_at.desc()).limit(
                min(max(limit, 1), 200)
            )
        )
        .scalars()
        .all()
    )


# --- Purchase orders ---


def create_purchase_order(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    location_id: uuid.UUID,
    supplier_id: uuid.UUID,
    lines: list[dict[str, object]],
    notes: str | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> PurchaseOrder:
    from app.modules.subscriptions.commercial_policy import assert_feature

    assert_feature(
        db, tenant_id=tenant_id, feature_key="inventory", operation="inventory.po.create"
    )
    clinics_service.get_location(db, tenant_id=tenant_id, location_id=location_id)
    _check_location(location_ids, location_id)
    get_supplier(db, tenant_id=tenant_id, supplier_id=supplier_id)
    if not lines:
        raise ValidationError("purchase order requires at least one line")
    ts = now()
    po = PurchaseOrder(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        location_id=location_id,
        supplier_id=supplier_id,
        status=M.PO_DRAFT,
        notes=(notes or "").strip() or None,
        created_by=actor_id,
        created_at=ts,
        updated_at=ts,
    )
    db.add(po)
    db.flush()
    seen: set[uuid.UUID] = set()
    for idx, raw in enumerate(lines, start=1):
        item_id = raw.get("item_id")
        if not isinstance(item_id, uuid.UUID):
            item_id = uuid.UUID(str(item_id))
        if item_id in seen:
            raise ValidationError("duplicate item on purchase order")
        seen.add(item_id)
        get_item(db, tenant_id=tenant_id, item_id=item_id)
        qty = _dec(raw.get("quantity"), field="quantity", min_value=QTY)
        cost = _dec(raw.get("unit_cost", "0"), field="unit_cost", min_value=Decimal("0"))
        db.add(
            PurchaseOrderLine(
                id=ids.uuid7(),
                tenant_id=tenant_id,
                purchase_order_id=po.id,
                item_id=item_id,
                quantity_ordered=qty,
                quantity_received=Decimal("0"),
                unit_cost=cost,
                line_no=idx,
            )
        )
    db.flush()
    return po


def get_purchase_order(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    purchase_order_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> PurchaseOrder:
    po = db.get(PurchaseOrder, purchase_order_id)
    if po is None or po.tenant_id != tenant_id:
        raise NotFoundError("purchase order not found")
    _check_location(location_ids, po.location_id)
    return po


def po_lines(db: DBSession, *, purchase_order_id: uuid.UUID) -> list[PurchaseOrderLine]:
    return list(
        db.execute(
            select(PurchaseOrderLine)
            .where(PurchaseOrderLine.purchase_order_id == purchase_order_id)
            .order_by(PurchaseOrderLine.line_no)
        )
        .scalars()
        .all()
    )


def submit_purchase_order(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    purchase_order_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> PurchaseOrder:
    po = get_purchase_order(
        db,
        tenant_id=tenant_id,
        purchase_order_id=purchase_order_id,
        location_ids=location_ids,
    )
    if po.status != M.PO_DRAFT:
        raise ConflictError("only draft purchase orders can be submitted")
    if not po_lines(db, purchase_order_id=po.id):
        raise ValidationError("purchase order has no lines")
    po.status = M.PO_ORDERED
    po.ordered_at = now()
    po.updated_at = now()
    db.flush()
    return po


def cancel_purchase_order(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    purchase_order_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> PurchaseOrder:
    po = get_purchase_order(
        db,
        tenant_id=tenant_id,
        purchase_order_id=purchase_order_id,
        location_ids=location_ids,
    )
    if po.status in (M.PO_RECEIVED, M.PO_CANCELLED):
        raise ConflictError("purchase order cannot be cancelled")
    if po.status == M.PO_PARTIAL:
        raise ConflictError("partially received purchase orders cannot be cancelled")
    po.status = M.PO_CANCELLED
    po.updated_at = now()
    db.flush()
    return po


def list_purchase_orders(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID | None = None,
    status: str | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
    limit: int = 50,
) -> list[PurchaseOrder]:
    stmt = select(PurchaseOrder).where(PurchaseOrder.tenant_id == tenant_id)
    if location_id is not None:
        _check_location(location_ids, location_id)
        stmt = stmt.where(PurchaseOrder.location_id == location_id)
    elif location_ids:
        stmt = stmt.where(PurchaseOrder.location_id.in_(list(location_ids)))
    if status is not None:
        if status not in M.PO_STATUSES:
            raise ValidationError("unknown status")
        stmt = stmt.where(PurchaseOrder.status == status)
    return list(
        db.execute(
            stmt.order_by(PurchaseOrder.created_at.desc()).limit(min(max(limit, 1), 200))
        )
        .scalars()
        .all()
    )


def receive_goods(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    purchase_order_id: uuid.UUID,
    receipt_key: str,
    lines: list[dict[str, object]],
    location_ids: frozenset[uuid.UUID] | None = None,
) -> GoodsReceipt:
    """Post a goods receipt and create ledger entries atomically.

    Duplicate ``receipt_key`` returns the existing posted receipt (idempotent).
    """
    key = (receipt_key or "").strip()
    if len(key) < 2 or len(key) > 80:
        raise ValidationError("receipt_key must be 2-80 characters")

    existing = db.execute(
        select(GoodsReceipt).where(
            GoodsReceipt.tenant_id == tenant_id, GoodsReceipt.receipt_key == key
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    po = get_purchase_order(
        db,
        tenant_id=tenant_id,
        purchase_order_id=purchase_order_id,
        location_ids=location_ids,
    )
    if po.status not in (M.PO_ORDERED, M.PO_PARTIAL):
        raise ConflictError("purchase order is not receivable")
    if not lines:
        raise ValidationError("receipt requires at least one line")

    # Lock PO row for concurrent receipt serialization.
    db.execute(
        select(PurchaseOrder).where(PurchaseOrder.id == po.id).with_for_update()
    )
    po = get_purchase_order(
        db, tenant_id=tenant_id, purchase_order_id=purchase_order_id, location_ids=location_ids
    )

    ts = now()
    gr = GoodsReceipt(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        purchase_order_id=po.id,
        location_id=po.location_id,
        status=M.GR_POSTED,
        receipt_key=key,
        received_by=actor_id,
        received_at=ts,
        created_at=ts,
    )
    db.add(gr)
    db.flush()

    line_map = {ln.id: ln for ln in po_lines(db, purchase_order_id=po.id)}
    for raw in lines:
        line_id = raw.get("purchase_order_line_id")
        if not isinstance(line_id, uuid.UUID):
            line_id = uuid.UUID(str(line_id))
        pol = line_map.get(line_id)
        if pol is None:
            raise ValidationError("unknown purchase order line")
        qty = _dec(raw.get("quantity"), field="quantity", min_value=QTY)
        remaining = pol.quantity_ordered - pol.quantity_received
        if qty > remaining:
            raise ConflictError("receipt quantity exceeds remaining ordered quantity")
        unit_cost_raw = raw.get("unit_cost")
        unit_cost = _dec(
            pol.unit_cost if unit_cost_raw is None else unit_cost_raw,
            field="unit_cost",
            min_value=Decimal("0"),
        )
        mv = _apply_delta(
            db,
            tenant_id=tenant_id,
            location_id=po.location_id,
            item_id=pol.item_id,
            kind=M.MV_PURCHASE_RECEIPT,
            quantity_delta=qty,
            actor_id=actor_id,
            unit_cost=unit_cost,
            reason="goods receipt",
            reference_type="goods_receipt",
            reference_id=gr.id,
            idempotency_key=f"gr:{key}:{pol.id}",
        )
        pol.quantity_received = pol.quantity_received + qty
        db.add(
            GoodsReceiptLine(
                id=ids.uuid7(),
                tenant_id=tenant_id,
                goods_receipt_id=gr.id,
                purchase_order_line_id=pol.id,
                item_id=pol.item_id,
                quantity=qty,
                unit_cost=unit_cost,
                movement_id=mv.id,
            )
        )

    # Refresh PO status from line totals.
    all_lines = po_lines(db, purchase_order_id=po.id)
    if all(ln.quantity_received >= ln.quantity_ordered for ln in all_lines):
        po.status = M.PO_RECEIVED
    elif any(ln.quantity_received > 0 for ln in all_lines):
        po.status = M.PO_PARTIAL
    po.updated_at = now()
    db.flush()
    return gr


class DashboardSummary(TypedDict):
    active_items: int
    low_stock_count: int
    out_of_stock_count: int
    stock_valuation: str
    recent_movements: list[InventoryMovement]
    recent_purchase_orders: list[PurchaseOrder]


def dashboard_summary(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> DashboardSummary:
    items = list_items(db, tenant_id=tenant_id, active_only=True, limit=200)
    balances = list_balances(
        db,
        tenant_id=tenant_id,
        location_id=location_id,
        location_ids=location_ids,
        limit=500,
    )
    low = [
        (b, i)
        for b, i in balances
        if b.quantity_on_hand <= i.reorder_level
    ]
    out = [(b, i) for b, i in balances if b.quantity_on_hand == 0]
    valuation = Decimal("0")
    for b, i in balances:
        valuation += b.quantity_on_hand * i.cost_price
    recent = list_movements(
        db,
        tenant_id=tenant_id,
        location_id=location_id,
        location_ids=location_ids,
        limit=10,
    )
    recent_pos = list_purchase_orders(
        db,
        tenant_id=tenant_id,
        location_id=location_id,
        location_ids=location_ids,
        limit=5,
    )
    return {
        "active_items": len(items),
        "low_stock_count": len(low),
        "out_of_stock_count": len(out),
        "stock_valuation": str(valuation.quantize(MONEY)),
        "recent_movements": recent,
        "recent_purchase_orders": recent_pos,
    }


def reconcile_balance(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID,
    item_id: uuid.UUID,
) -> Decimal:
    """Sum ledger deltas and compare to projection (read-only check helper)."""
    total = db.execute(
        text(
            "SELECT COALESCE(SUM(quantity_delta), 0) FROM inventory_movements "
            "WHERE tenant_id = :t AND location_id = :l AND item_id = :i"
        ),
        {"t": str(tenant_id), "l": str(location_id), "i": str(item_id)},
    ).scalar()
    ledger = Decimal(str(total))
    projected = get_balance(
        db, tenant_id=tenant_id, location_id=location_id, item_id=item_id
    )
    if ledger != projected:
        raise ConflictError("ledger and balance projection diverge")
    return projected
