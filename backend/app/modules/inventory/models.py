"""Inventory models. Stock truth lives in the immutable movement ledger;
`inventory_balances` is a transactional projection updated with the ledger.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db import Base

# --- Movement kinds (ledger) ---

MV_OPENING = "opening"
MV_PURCHASE_RECEIPT = "purchase_receipt"
MV_ADJUSTMENT = "adjustment"
MV_CONSUMPTION = "consumption"
MV_WASTAGE = "wastage"
MV_RETURN = "return"
MV_TRANSFER_OUT = "transfer_out"
MV_TRANSFER_IN = "transfer_in"
MOVEMENT_KINDS = (
    MV_OPENING,
    MV_PURCHASE_RECEIPT,
    MV_ADJUSTMENT,
    MV_CONSUMPTION,
    MV_WASTAGE,
    MV_RETURN,
    MV_TRANSFER_OUT,
    MV_TRANSFER_IN,
)

# --- Purchase order ---

PO_DRAFT = "draft"
PO_ORDERED = "ordered"
PO_PARTIAL = "partially_received"
PO_RECEIVED = "received"
PO_CANCELLED = "cancelled"
PO_STATUSES = (PO_DRAFT, PO_ORDERED, PO_PARTIAL, PO_RECEIVED, PO_CANCELLED)

GR_POSTED = "posted"
GR_VOIDED = "voided"
GR_STATUSES = (GR_POSTED, GR_VOIDED)


class InventoryItem(Base):
    """Tenant-scoped catalog item. Stock is per location via balances."""

    __tablename__ = "inventory_items"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False, default="general")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str] = mapped_column(String(32), nullable=False, default="each")
    cost_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    reorder_level: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_inv_items_tenant", "tenant_id"),
        sa.UniqueConstraint("tenant_id", "sku", name="uq_inv_items_tenant_sku"),
        CheckConstraint("cost_price >= 0", name="ck_inv_items_cost"),
        CheckConstraint("reorder_level >= 0", name="ck_inv_items_reorder"),
    )


class InventorySupplier(Base):
    __tablename__ = "inventory_suppliers"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_inv_suppliers_tenant", "tenant_id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_inv_suppliers_tenant_name"),
    )


class InventoryBalance(Base):
    """Projected on-hand quantity per location+item. Updated only with ledger writes."""

    __tablename__ = "inventory_balances"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_items.id", ondelete="RESTRICT"), nullable=False
    )
    quantity_on_hand: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id", "location_id", "item_id", name="uq_inv_balance_location_item"
        ),
        Index("ix_inv_balances_tenant", "tenant_id"),
        Index("ix_inv_balances_location", "location_id"),
        CheckConstraint("quantity_on_hand >= 0", name="ck_inv_balance_nonneg"),
    )


class InventoryMovement(Base):
    """Immutable stock ledger row. quantity_delta signed; never updated/deleted."""

    __tablename__ = "inventory_movements"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_items.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[str] = mapped_column(
        sa.Enum(
            *MOVEMENT_KINDS,
            name="inventory_movement_kind",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
    )
    quantity_delta: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reference_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    transfer_group_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(80), nullable=True)

    __table_args__ = (
        Index("ix_inv_movements_tenant", "tenant_id"),
        Index("ix_inv_movements_location", "location_id"),
        Index("ix_inv_movements_item", "item_id"),
        Index("ix_inv_movements_occurred", "tenant_id", "occurred_at"),
        sa.UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_inv_movements_idem"
        ),
        CheckConstraint("quantity_delta != 0", name="ck_inv_movement_nonzero"),
    )


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("inventory_suppliers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        sa.Enum(
            *PO_STATUSES,
            name="purchase_order_status",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
        default=PO_DRAFT,
    )
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    ordered_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_po_tenant", "tenant_id"),
        Index("ix_po_location", "location_id"),
        Index("ix_po_supplier", "supplier_id"),
    )


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_lines"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_items.id", ondelete="RESTRICT"), nullable=False
    )
    quantity_ordered: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    quantity_received: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        Index("ix_po_lines_po", "purchase_order_id"),
        CheckConstraint("quantity_ordered > 0", name="ck_po_line_qty"),
        CheckConstraint("quantity_received >= 0", name="ck_po_line_recv"),
        CheckConstraint("unit_cost >= 0", name="ck_po_line_cost"),
        sa.UniqueConstraint("purchase_order_id", "item_id", name="uq_po_line_item"),
    )


class GoodsReceipt(Base):
    """Posted goods receipt against a PO. Idempotent via receipt_key."""

    __tablename__ = "goods_receipts"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("purchase_orders.id", ondelete="RESTRICT"), nullable=False
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        sa.Enum(*GR_STATUSES, name="goods_receipt_status", native_enum=True, validate_strings=True),
        nullable=False,
        default=GR_POSTED,
    )
    receipt_key: Mapped[str] = mapped_column(String(80), nullable=False)
    received_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    received_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_gr_tenant", "tenant_id"),
        Index("ix_gr_po", "purchase_order_id"),
        sa.UniqueConstraint("tenant_id", "receipt_key", name="uq_gr_receipt_key"),
    )


class GoodsReceiptLine(Base):
    __tablename__ = "goods_receipt_lines"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    goods_receipt_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("goods_receipts.id", ondelete="CASCADE"), nullable=False
    )
    purchase_order_line_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("purchase_order_lines.id", ondelete="RESTRICT"),
        nullable=False,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_items.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    movement_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("inventory_movements.id", ondelete="RESTRICT"),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_gr_lines_receipt", "goods_receipt_id"),
        CheckConstraint("quantity > 0", name="ck_gr_line_qty"),
    )
