"""Strict transport contracts for private unit-economics APIs."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .domain import CostType, EconomicsScopeType


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProviderUsageCreate(_StrictModel):
    organization_id: str = Field(min_length=1, max_length=36)
    workspace_id: str | None = Field(default=None, max_length=36)
    order_id: str | None = Field(default=None, max_length=36)
    order_item_id: str | None = Field(default=None, max_length=36)
    catalog_item_id: str | None = Field(default=None, max_length=50)
    asset_id: str | None = Field(default=None, max_length=36)
    acquisition_id: str | None = Field(default=None, max_length=36)
    dataset_id: str | None = Field(default=None, max_length=36)
    processing_job_id: str | None = Field(default=None, max_length=36)
    fulfilment_job_id: str | None = Field(default=None, max_length=36)
    intelligence_acquisition_id: str | None = Field(default=None, max_length=36)
    notification_delivery_id: str | None = Field(default=None, max_length=36)
    report_id: str | None = Field(default=None, max_length=36)
    provider: str = Field(min_length=1, max_length=80)
    service: str = Field(min_length=1, max_length=100)
    usage_type: str = Field(min_length=1, max_length=60)
    quantity: Decimal = Field(gt=0, le=Decimal("99999999999999.999999"))
    unit: str = Field(min_length=1, max_length=40)
    currency: str | None = Field(default=None, min_length=3, max_length=5)
    unit_cost: Decimal | None = Field(
        default=None, ge=0, le=Decimal("99999999999999.999999")
    )
    total_cost: Decimal | None = Field(
        default=None, ge=0, le=Decimal("9999999999999999.9999")
    )
    occurred_at: datetime
    provider_reference: str | None = Field(default=None, max_length=200)
    idempotency_key: str = Field(min_length=8, max_length=160)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("provider", "service", "usage_type", "unit")
    @classmethod
    def normalize_codes(cls, value: str) -> str:
        normalized = value.strip().lower().replace(" ", "_")
        if not normalized:
            raise ValueError("value cannot be blank")
        return normalized

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        if not value:
            return value
        normalized = value.strip().upper()
        if not normalized.isalpha():
            raise ValueError("currency must be an alphabetic ISO-style code")
        return normalized

    @field_validator("quantity", "unit_cost")
    @classmethod
    def six_decimal_places(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and value.as_tuple().exponent < -6:
            raise ValueError("value supports at most 6 decimal places")
        return value

    @field_validator("total_cost")
    @classmethod
    def four_decimal_places(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and value.as_tuple().exponent < -4:
            raise ValueError("total_cost supports at most 4 decimal places")
        return value

    @model_validator(mode="after")
    def validate_cost_fields(self):
        has_cost = self.unit_cost is not None or self.total_cost is not None
        if has_cost and not self.currency:
            raise ValueError("currency is required when provider cost is supplied")
        if not has_cost and self.currency:
            raise ValueError("currency is only valid when provider cost is supplied")
        if self.unit_cost is not None:
            try:
                with localcontext() as context:
                    context.prec = 50
                    calculated = (self.quantity * self.unit_cost).quantize(
                        Decimal("0.0001"), rounding=ROUND_HALF_UP
                    )
            except InvalidOperation as exc:
                raise ValueError("calculated provider cost is outside the supported range") from exc
            if calculated > Decimal("9999999999999999.9999"):
                raise ValueError("calculated provider cost is outside the supported range")
            if self.total_cost is not None and calculated != self.total_cost:
                raise ValueError("total_cost must equal quantity multiplied by unit_cost")
        return self


class InternalCostCreate(_StrictModel):
    order_id: str = Field(min_length=1, max_length=36)
    order_item_id: str | None = Field(default=None, max_length=36)
    catalog_item_id: str | None = Field(default=None, max_length=50)
    asset_id: str | None = Field(default=None, max_length=36)
    fulfilment_job_id: str | None = Field(default=None, max_length=36)
    contractor_assignment_id: str | None = Field(default=None, max_length=36)
    cost_type: CostType
    description: str = Field(min_length=2, max_length=500)
    amount: Decimal = Field(gt=0, le=Decimal("9999999999999999.9999"))
    currency: str = Field(min_length=3, max_length=5)
    incurred_at: datetime
    reference: str | None = Field(default=None, max_length=200)
    idempotency_key: str = Field(min_length=8, max_length=160)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized.isalpha():
            raise ValueError("currency must be an alphabetic ISO-style code")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 2:
            raise ValueError("description must contain at least 2 visible characters")
        return normalized

    @field_validator("amount")
    @classmethod
    def four_decimal_places(cls, value: Decimal) -> Decimal:
        if value.as_tuple().exponent < -4:
            raise ValueError("amount supports at most 4 decimal places")
        return value


class ProviderUsageOut(BaseModel):
    id: str
    organization_id: str
    workspace_id: str | None
    order_id: str | None
    order_item_id: str | None
    catalog_item_id: str | None
    asset_id: str | None
    acquisition_id: str | None
    dataset_id: str | None
    processing_job_id: str | None
    fulfilment_job_id: str | None
    intelligence_acquisition_id: str | None
    notification_delivery_id: str | None
    report_id: str | None
    provider: str
    service: str
    usage_type: str
    quantity: Decimal
    unit: str
    currency: str | None
    unit_cost: Decimal | None
    total_cost: Decimal | None
    occurred_at: datetime
    provider_reference: str | None
    idempotency_key: str
    metadata: dict[str, Any]
    created_by_user_id: str | None
    created_at: datetime


class InternalCostOut(BaseModel):
    id: str
    organization_id: str
    workspace_id: str | None
    order_id: str
    order_item_id: str | None
    catalog_item_id: str | None
    asset_id: str | None
    fulfilment_job_id: str | None
    contractor_assignment_id: str | None
    cost_type: str
    description: str
    amount: Decimal
    currency: str
    incurred_at: datetime
    reference: str | None
    idempotency_key: str
    metadata: dict[str, Any]
    created_by_user_id: str | None
    created_at: datetime


class ProviderUsageListOut(BaseModel):
    items: list[ProviderUsageOut]
    total: int


class InternalCostListOut(BaseModel):
    items: list[InternalCostOut]
    total: int


class CostBreakdownOut(BaseModel):
    cost_type: str
    amount: Decimal


class EconomicsCurrencySummaryOut(BaseModel):
    currency: str
    revenue: Decimal
    internal_cost: Decimal
    provider_cost: Decimal
    direct_cost: Decimal
    gross_contribution: Decimal
    gross_margin_percent: Decimal | None
    order_count: int
    line_item_count: int
    cost_breakdown: list[CostBreakdownOut]


class UnitEconomicsOut(BaseModel):
    scope_type: EconomicsScopeType
    scope_id: str
    scope_name: str
    currencies: list[EconomicsCurrencySummaryOut]
    generated_at: datetime


__all__ = [
    "CostBreakdownOut",
    "EconomicsCurrencySummaryOut",
    "InternalCostCreate",
    "InternalCostListOut",
    "InternalCostOut",
    "ProviderUsageCreate",
    "ProviderUsageListOut",
    "ProviderUsageOut",
    "UnitEconomicsOut",
]
