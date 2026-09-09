"""HTTP-safe schemas for the generic Asset domain."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.modules.assets.domain import (
    AssetStatus,
    normalize_asset_type,
    normalize_geometry,
    normalize_sector,
)


class AssetCreate(BaseModel):
    parent_asset_id: str | None = Field(default=None, max_length=36)
    sector: str = Field(min_length=2, max_length=50)
    asset_type: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    status: AssetStatus = AssetStatus.ACTIVE
    external_reference: str | None = Field(default=None, max_length=200)
    location_label: str | None = Field(default=None, max_length=500)
    geometry: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    _sector = field_validator("sector")(normalize_sector)
    _asset_type = field_validator("asset_type")(normalize_asset_type)
    _geometry = field_validator("geometry")(normalize_geometry)


class AssetUpdate(BaseModel):
    parent_asset_id: str | None = Field(default=None, max_length=36)
    sector: str | None = Field(default=None, min_length=2, max_length=50)
    asset_type: str | None = Field(default=None, min_length=2, max_length=80)
    name: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    status: AssetStatus | None = None
    external_reference: str | None = Field(default=None, max_length=200)
    location_label: str | None = Field(default=None, max_length=500)
    geometry: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("sector")
    @classmethod
    def canonical_sector(cls, value: str | None) -> str | None:
        return normalize_sector(value) if value is not None else None

    @field_validator("asset_type")
    @classmethod
    def canonical_asset_type(cls, value: str | None) -> str | None:
        return normalize_asset_type(value) if value is not None else None

    @field_validator("geometry")
    @classmethod
    def canonical_geometry(cls, value: dict[str, Any] | None):
        return normalize_geometry(value)


class AssetOut(BaseModel):
    id: str
    organization_id: str
    workspace_id: str | None
    parent_asset_id: str | None
    sector: str
    asset_type: str
    name: str
    description: str | None
    status: AssetStatus
    external_reference: str | None
    location_label: str | None
    geometry: dict[str, Any] | None
    bbox: list[float] | None
    center: dict[str, float] | None
    metadata: dict[str, Any]
    children_count: int = 0
    legacy_source: str | None = None
    legacy_source_id: str | None = None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AssetRegistryOut(BaseModel):
    sectors: list[str]
    common_asset_types: list[str]
    geometry_types: list[str]
    srid: int = 4326
    portable_geometry_field: str = "geometry_geojson"


__all__ = [
    "AssetCreate",
    "AssetOut",
    "AssetRegistryOut",
    "AssetUpdate",
]
