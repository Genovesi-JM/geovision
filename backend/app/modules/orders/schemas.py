"""HTTP-neutral transport contracts for commercial orders."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.orders.domain import FulfilmentStatus


class CheckoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_method: str = Field(min_length=2, max_length=40)
    currency: str = Field(default="EUR", min_length=3, max_length=5)
    billing_info: dict[str, Any]
    customer_notes: str | None = Field(default=None, max_length=2_000)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()


class DraftItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    catalog_item_id: str = Field(min_length=1, max_length=50)
    quantity: int = Field(default=1, ge=1, le=10_000)
    unit_amount: int | None = Field(default=None, ge=0)
    discount_amount: int = Field(default=0, ge=0)


class DraftOrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: str = Field(min_length=1, max_length=36)
    workspace_id: str | None = Field(default=None, max_length=36)
    customer_id: str | None = Field(default=None, max_length=36)
    currency: str = Field(default="EUR", min_length=3, max_length=5)
    items: list[DraftItemCreate] = Field(min_length=1, max_length=200)
    customer_notes: str | None = Field(default=None, max_length=2_000)
    internal_notes: str | None = Field(default=None, max_length=10_000)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()


class FulfilmentTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: FulfilmentStatus
    reason: str | None = Field(default=None, max_length=2_000)
    customer_visible: bool = True
    expected_version: int | None = Field(default=None, ge=1)


class OrderItemOut(BaseModel):
    id: str
    catalog_item_id: str | None
    catalog_item_type: str | None
    code: str | None
    name: str | None
    quantity: int
    unit_amount: int
    discount_amount: int
    line_total: int
    tax_rate: float
    tax_amount: int
    currency: str
    status: str | None
    scheduled_date: str | None
    pricing_snapshot: dict[str, Any]
    fulfilment_hints: dict[str, Any]


class OrderEventOut(BaseModel):
    id: str
    event_type: str
    title: str
    description: str | None
    actor_name: str | None
    created_at: str


class DeliverableOut(BaseModel):
    id: str
    order_item_id: str | None
    name: str
    description: str | None
    deliverable_type: str
    file_size: int | None
    mime_type: str | None
    download_url: str | None
    is_ready: bool
    created_at: str


class OrderSummaryOut(BaseModel):
    id: str
    order_number: str | None
    order_type: str
    fulfilment_status: str
    payment_status: str
    currency: str
    subtotal: int
    discount_total: int
    tax_amount: int
    shipping_fee: int
    total: int
    item_count: int
    lifecycle_version: int
    created_at: str
    updated_at: str


class OrderDetailOut(OrderSummaryOut):
    organization_id: str | None
    workspace_id: str | None
    customer_id: str | None
    site_id: str | None
    payment_method: str | None
    customer_notes: str | None
    delivery_method: str | None
    assigned_team: str | None
    scheduled_start: str | None
    scheduled_end: str | None
    actual_start: str | None
    actual_end: str | None
    estimated_delivery: str | None
    actual_delivery: str | None
    completed_at: str | None
    cancelled_at: str | None
    items: list[OrderItemOut]
    events: list[OrderEventOut]
    deliverables: list[DeliverableOut]


class InternalOrderOut(OrderDetailOut):
    legacy_status: str
    payment_id: str | None
    payment_reference: str | None
    internal_notes: str | None
    on_hold_reason: str | None
    failed_at: str | None


class CheckoutOut(BaseModel):
    success: bool
    order_id: str | None
    order_number: str | None
    payment_required: bool
    payment_method: str | None
    payment_data: dict[str, Any] | None
    error: str | None


__all__ = [
    "CheckoutOut",
    "CheckoutRequest",
    "DeliverableOut",
    "DraftItemCreate",
    "DraftOrderCreate",
    "FulfilmentTransitionRequest",
    "InternalOrderOut",
    "OrderDetailOut",
    "OrderEventOut",
    "OrderItemOut",
    "OrderSummaryOut",
]
