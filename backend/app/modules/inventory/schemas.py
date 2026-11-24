"""Inventory API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_serializer

from app.platform.time import to_api_utc


class ItemCreateRequest(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=2, max_length=200)
    category: str = Field(default="general", max_length=80)
    description: str | None = None
    unit: str = Field(default="each", max_length=32)
    cost_price: str = "0"
    reorder_level: str = "0"


class ItemUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    category: str | None = Field(default=None, max_length=80)
    description: str | None = None
    unit: str | None = Field(default=None, max_length=32)
    cost_price: str | None = None
    reorder_level: str | None = None
    is_active: bool | None = None


class ItemResponse(BaseModel):
    id: uuid.UUID
    sku: str
    name: str
    category: str
    description: str | None
    unit: str
    cost_price: str
    reorder_level: str
    is_active: bool


class SupplierCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    contact_name: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    tax_id: str | None = None


class SupplierResponse(BaseModel):
    id: uuid.UUID
    name: str
    contact_name: str | None
    phone: str | None
    email: str | None
    address: str | None
    tax_id: str | None
    is_active: bool


class OpeningStockRequest(BaseModel):
    location_id: uuid.UUID
    item_id: uuid.UUID
    quantity: str
    unit_cost: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=80)


class AdjustStockRequest(BaseModel):
    location_id: uuid.UUID
    item_id: uuid.UUID
    quantity_delta: str
    reason: str = Field(min_length=2, max_length=200)
    idempotency_key: str | None = Field(default=None, max_length=80)


class ConsumeStockRequest(BaseModel):
    location_id: uuid.UUID
    item_id: uuid.UUID
    quantity: str
    reason: str = Field(min_length=2, max_length=200)
    reference_type: str | None = Field(default=None, max_length=40)
    reference_id: uuid.UUID | None = None
    idempotency_key: str | None = Field(default=None, max_length=80)


class WastageRequest(BaseModel):
    location_id: uuid.UUID
    item_id: uuid.UUID
    quantity: str
    reason: str = Field(min_length=2, max_length=200)
    idempotency_key: str | None = Field(default=None, max_length=80)


class ReturnStockRequest(BaseModel):
    location_id: uuid.UUID
    item_id: uuid.UUID
    quantity: str
    reason: str = Field(min_length=2, max_length=200)
    idempotency_key: str | None = Field(default=None, max_length=80)


class TransferStockRequest(BaseModel):
    from_location_id: uuid.UUID
    to_location_id: uuid.UUID
    item_id: uuid.UUID
    quantity: str
    idempotency_key: str | None = Field(default=None, max_length=80)


class MovementResponse(BaseModel):
    id: uuid.UUID
    location_id: uuid.UUID
    item_id: uuid.UUID
    kind: str
    quantity_delta: str
    unit_cost: str | None
    reason: str | None
    reference_type: str | None
    reference_id: uuid.UUID | None
    occurred_at: datetime

    @field_serializer("occurred_at")
    def _ser(self, value: datetime) -> str:
        return to_api_utc(value)


class BalanceResponse(BaseModel):
    item_id: uuid.UUID
    location_id: uuid.UUID
    sku: str
    name: str
    unit: str
    quantity_on_hand: str
    reorder_level: str
    cost_price: str
    is_low: bool


class POLineCreate(BaseModel):
    item_id: uuid.UUID
    quantity: str
    unit_cost: str = "0"


class PurchaseOrderCreateRequest(BaseModel):
    location_id: uuid.UUID
    supplier_id: uuid.UUID
    lines: list[POLineCreate] = Field(min_length=1)
    notes: str | None = None


class PurchaseOrderLineResponse(BaseModel):
    id: uuid.UUID
    item_id: uuid.UUID
    quantity_ordered: str
    quantity_received: str
    unit_cost: str
    line_no: int


class PurchaseOrderResponse(BaseModel):
    id: uuid.UUID
    location_id: uuid.UUID
    supplier_id: uuid.UUID
    status: str
    notes: str | None
    ordered_at: datetime | None
    created_at: datetime
    lines: list[PurchaseOrderLineResponse] = []

    @field_serializer("ordered_at", "created_at")
    def _ser(self, value: datetime | None) -> str | None:
        return None if value is None else to_api_utc(value)


class ReceiptLineRequest(BaseModel):
    purchase_order_line_id: uuid.UUID
    quantity: str
    unit_cost: str | None = None


class GoodsReceiptRequest(BaseModel):
    receipt_key: str = Field(min_length=2, max_length=80)
    lines: list[ReceiptLineRequest] = Field(min_length=1)


class GoodsReceiptResponse(BaseModel):
    id: uuid.UUID
    purchase_order_id: uuid.UUID
    location_id: uuid.UUID
    status: str
    receipt_key: str
    received_at: datetime

    @field_serializer("received_at")
    def _ser(self, value: datetime) -> str:
        return to_api_utc(value)


class DashboardResponse(BaseModel):
    active_items: int
    low_stock_count: int
    out_of_stock_count: int
    stock_valuation: str
    recent_movements: list[MovementResponse]
    recent_purchase_orders: list[PurchaseOrderResponse]
