"""Transport contracts for the GeoVision-owned commercial catalogue."""

from __future__ import annotations

from enum import Enum
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CatalogItemType(str, Enum):
    PHYSICAL_PRODUCT = "PHYSICAL_PRODUCT"
    SERVICE = "SERVICE"
    MONITORING_PLAN = "MONITORING_PLAN"
    INSTALLATION = "INSTALLATION"
    INSPECTION = "INSPECTION"
    ANALYSIS = "ANALYSIS"


class CatalogItemStatus(str, Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    UNAVAILABLE = "UNAVAILABLE"
    ARCHIVED = "ARCHIVED"


class AvailabilityStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    PREORDER = "PREORDER"
    ON_REQUEST = "ON_REQUEST"


class PriceModel(str, Enum):
    FIXED = "FIXED"
    STARTING_AT = "STARTING_AT"
    QUOTE = "QUOTE"
    SUBSCRIPTION = "SUBSCRIPTION"
    USAGE = "USAGE"


_SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "private_key",
    "credential",
    "connection_string",
)


def _reject_sensitive_keys(value: Any, path: str = "metadata") -> Any:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if any(part in normalized for part in _SENSITIVE_KEY_PARTS):
                raise ValueError(f"{path} cannot contain credential-like key '{key}'")
            _reject_sensitive_keys(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_sensitive_keys(nested, f"{path}[{index}]")
    return value


class CatalogItemWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=200)
    summary: str | None = Field(default=None, max_length=500)
    description: str | None = None
    item_type: CatalogItemType
    category: str | None = Field(default=None, max_length=80)
    sectors: list[str] = Field(default_factory=list, max_length=20)
    asset_types: list[str] = Field(default_factory=list, max_length=50)
    customer_content: dict[str, Any] = Field(default_factory=dict)
    deliverables: list[str] = Field(default_factory=list, max_length=100)
    price_model: PriceModel = PriceModel.FIXED
    currency: str = Field(default="AOA", min_length=3, max_length=5)
    unit_amount: int | None = Field(default=None, ge=0)
    pricing: dict[str, int] = Field(default_factory=dict)
    availability_status: AvailabilityStatus = AvailabilityStatus.AVAILABLE
    status: CatalogItemStatus = CatalogItemStatus.DRAFT
    recommendation_triggers: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    image_url: str | None = None
    is_featured: bool = False
    requires_site: bool = False
    requires_scheduling: bool = False
    duration_hours: int | None = Field(default=None, gt=0)
    fulfilment_type: str | None = Field(default=None, max_length=40)
    installed_product_type: str | None = Field(default=None, max_length=80)
    supplier_id: str | None = Field(default=None, max_length=36)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("pricing")
    @classmethod
    def validate_pricing(cls, value: dict[str, int]) -> dict[str, int]:
        normalized: dict[str, int] = {}
        for currency, amount in value.items():
            key = str(currency).strip().upper()
            if not 3 <= len(key) <= 5:
                raise ValueError("pricing currency keys must be ISO-style codes")
            if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
                raise ValueError("pricing values must be non-negative minor-unit integers")
            normalized[key] = amount
        return normalized

    @field_validator("metadata", "recommendation_triggers")
    @classmethod
    def reject_credentials(cls, value: Any) -> Any:
        return _reject_sensitive_keys(value)

    @model_validator(mode="after")
    def validate_published_price(self):
        if self.status == CatalogItemStatus.PUBLISHED and self.price_model != PriceModel.QUOTE:
            prices = dict(self.pricing)
            if self.unit_amount is not None:
                prices.setdefault(self.currency, self.unit_amount)
            if not prices:
                raise ValueError("published priced items require unit_amount or pricing")
        return self


class CatalogItemCreate(CatalogItemWrite):
    code: str | None = Field(default=None, max_length=100)
    slug: str | None = Field(default=None, max_length=200)


class CatalogItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str | None = Field(default=None, max_length=100)
    slug: str | None = Field(default=None, max_length=200)
    name: str | None = Field(default=None, min_length=2, max_length=200)
    summary: str | None = Field(default=None, max_length=500)
    description: str | None = None
    item_type: CatalogItemType | None = None
    category: str | None = Field(default=None, max_length=80)
    sectors: list[str] | None = Field(default=None, max_length=20)
    asset_types: list[str] | None = Field(default=None, max_length=50)
    customer_content: dict[str, Any] | None = None
    deliverables: list[str] | None = Field(default=None, max_length=100)
    price_model: PriceModel | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=5)
    unit_amount: int | None = Field(default=None, ge=0)
    pricing: dict[str, int] | None = None
    availability_status: AvailabilityStatus | None = None
    status: CatalogItemStatus | None = None
    recommendation_triggers: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] | None = None
    image_url: str | None = None
    is_featured: bool | None = None
    requires_site: bool | None = None
    requires_scheduling: bool | None = None
    duration_hours: int | None = Field(default=None, gt=0)
    fulfilment_type: str | None = Field(default=None, max_length=40)
    installed_product_type: str | None = Field(default=None, max_length=80)
    supplier_id: str | None = Field(default=None, max_length=36)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value

    @field_validator("pricing")
    @classmethod
    def validate_pricing(cls, value: dict[str, int] | None) -> dict[str, int] | None:
        return CatalogItemWrite.validate_pricing(value) if value is not None else value

    @field_validator("metadata", "recommendation_triggers")
    @classmethod
    def reject_credentials(cls, value: Any) -> Any:
        return _reject_sensitive_keys(value) if value is not None else value


class CatalogItemPublic(BaseModel):
    id: str
    code: str
    slug: str
    name: str
    summary: str | None
    description: str | None
    item_type: CatalogItemType
    category: str | None
    sectors: list[str]
    asset_types: list[str]
    customer_content: dict[str, Any]
    deliverables: list[str]
    price_model: PriceModel
    currency: str
    unit_amount: int | None
    pricing: dict[str, int]
    availability_status: AvailabilityStatus
    recommendation_triggers: list[dict[str, Any]]
    image_url: str | None
    is_featured: bool
    requires_site: bool
    requires_scheduling: bool
    duration_hours: int | None
    fulfilment_type: str | None
    installed_product_type: str | None
    translations: dict[str, dict[str, Any]] = Field(default_factory=dict)


class CatalogItemInternal(CatalogItemPublic):
    status: CatalogItemStatus
    metadata: dict[str, Any]
    supplier_id: str | None
    legacy_source: str | None
    legacy_source_id: str | None
    published_at: str | None
    created_at: str
    updated_at: str


class SupplierCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=2, max_length=80)
    legal_name: str = Field(min_length=2, max_length=200)
    status: str = Field(default="ACTIVE", pattern="^(ACTIVE|ON_HOLD|INACTIVE)$")
    contact_email: str | None = Field(default=None, max_length=320)
    contact_phone: str | None = Field(default=None, max_length=50)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    region: str | None = Field(default=None, max_length=120)
    service_area: list[str | dict[str, Any]] = Field(default_factory=list, max_length=100)
    capabilities: list[str] = Field(default_factory=list, max_length=100)
    certifications: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    insurance: dict[str, Any] = Field(default_factory=dict)
    document_refs: list[dict[str, Any]] = Field(default_factory=list, max_length=200)
    quality_score: float | None = Field(default=None, ge=0, le=100)
    last_reviewed_at: datetime | None = None
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("country_code")
    @classmethod
    def normalize_country(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value

    @field_validator("capabilities")
    @classmethod
    def normalize_capabilities(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip().upper() for value in values if value.strip()))

    @field_validator(
        "service_area", "certifications", "insurance", "document_refs", "metadata"
    )
    @classmethod
    def reject_credentials(cls, value: Any) -> Any:
        return _reject_sensitive_keys(value)


class SupplierUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    legal_name: str | None = Field(default=None, min_length=2, max_length=200)
    status: str | None = Field(default=None, pattern="^(ACTIVE|ON_HOLD|INACTIVE)$")
    contact_email: str | None = Field(default=None, max_length=320)
    contact_phone: str | None = Field(default=None, max_length=50)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    region: str | None = Field(default=None, max_length=120)
    service_area: list[str | dict[str, Any]] | None = Field(default=None, max_length=100)
    capabilities: list[str] | None = Field(default=None, max_length=100)
    certifications: list[dict[str, Any]] | None = Field(default=None, max_length=100)
    insurance: dict[str, Any] | None = None
    document_refs: list[dict[str, Any]] | None = Field(default=None, max_length=200)
    quality_score: float | None = Field(default=None, ge=0, le=100)
    last_reviewed_at: datetime | None = None
    notes: str | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("country_code")
    @classmethod
    def normalize_country(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value

    @field_validator("capabilities")
    @classmethod
    def normalize_capabilities(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        return list(dict.fromkeys(value.strip().upper() for value in values if value.strip()))

    @field_validator(
        "service_area", "certifications", "insurance", "document_refs", "metadata"
    )
    @classmethod
    def reject_credentials(cls, value: Any) -> Any:
        return _reject_sensitive_keys(value) if value is not None else value


class SupplierInternal(BaseModel):
    id: str
    code: str
    legal_name: str
    status: str
    contact_email: str | None
    contact_phone: str | None
    country_code: str | None
    region: str | None
    service_area: list[Any]
    capabilities: list[str]
    certifications: list[dict[str, Any]]
    insurance: dict[str, Any]
    document_refs: list[dict[str, Any]]
    quality_score: float | None
    last_reviewed_at: str | None
    notes: str | None
    metadata: dict[str, Any]
    created_at: str
    updated_at: str


__all__ = [
    "AvailabilityStatus",
    "CatalogItemCreate",
    "CatalogItemInternal",
    "CatalogItemPublic",
    "CatalogItemStatus",
    "CatalogItemType",
    "CatalogItemUpdate",
    "PriceModel",
    "SupplierCreate",
    "SupplierInternal",
    "SupplierUpdate",
]
