"""HTTP-neutral contracts for canonical datasets and secure uploads."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.assets.domain import normalize_sector as normalize_asset_sector
from app.sector_taxonomy import PUBLIC_SECTORS_BY_ASSET_SECTOR
from app.modules.datasets.domain import (
    DatasetStatus,
    ObjectArea,
    ProcessingLevel,
    QualityStatus,
    normalize_dataset_type,
    reject_sensitive_metadata,
)


class SourceTool(str, Enum):
    DJI_TERRA = "dji_terra"
    PIX4D = "pix4d"
    METASHAPE = "metashape"
    DRONEDEPLOY = "dronedeploy"
    ARCGIS = "arcgis"
    QGIS = "qgis"
    LIDAR_PROC = "lidar_processor"
    BIM360 = "bim360"
    PROCORE = "procore"
    MANUAL = "manual"
    API = "api"


class DatasetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_id: str | None = Field(default=None, max_length=36)
    asset_id: str | None = Field(default=None, max_length=36)
    mission_id: str | None = Field(default=None, max_length=36)
    name: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    source_tool: SourceTool = SourceTool.MANUAL
    dataset_type: str = Field(default="RGB_IMAGES", min_length=2, max_length=80)
    provider: str | None = Field(default=None, max_length=80)
    source: str | None = Field(default=None, max_length=100)
    source_reference: str | None = Field(default=None, max_length=240)
    sector: str | None = Field(default=None, max_length=50)
    capture_time: datetime | None = None
    capture_date: datetime | None = None
    crs: str | None = Field(default=None, max_length=100)
    resolution: float | None = Field(default=None, gt=0)
    resolution_unit: str | None = Field(default=None, max_length=30)
    processing_level: ProcessingLevel = ProcessingLevel.RAW
    quality_status: QualityStatus = QualityStatus.UNREVIEWED
    metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)

    @field_validator("dataset_type", mode="before")
    @classmethod
    def stable_dataset_type(cls, value: str) -> str:
        return normalize_dataset_type(value)

    @field_validator("sector", mode="before")
    @classmethod
    def technical_sector(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_asset_sector(value)
        if normalized not in PUBLIC_SECTORS_BY_ASSET_SECTOR:
            raise ValueError("sector must map to one of the six GeoVision sectors")
        return normalized

    @field_validator("metadata", "provenance")
    @classmethod
    def safe_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_sensitive_metadata(value)

    @model_validator(mode="after")
    def linked_asset_and_capture_time(self):
        if not self.asset_id and not self.site_id:
            raise ValueError("asset_id or legacy site_id is required")
        if (
            self.capture_time
            and self.capture_date
            and self.capture_time != self.capture_date
        ):
            raise ValueError("capture_time and capture_date must agree")
        if self.resolution is not None and not self.resolution_unit:
            raise ValueError("resolution_unit is required with resolution")
        return self


class DatasetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    status: DatasetStatus | None = None
    capture_time: datetime | None = None
    capture_date: datetime | None = None
    crs: str | None = Field(default=None, max_length=100)
    resolution: float | None = Field(default=None, gt=0)
    resolution_unit: str | None = Field(default=None, max_length=30)
    processing_level: ProcessingLevel | None = None
    quality_status: QualityStatus | None = None
    metadata: dict[str, Any] | None = None
    provenance: dict[str, Any] | None = None
    expected_version: int | None = Field(default=None, ge=1)

    @field_validator("metadata", "provenance")
    @classmethod
    def safe_metadata(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return reject_sensitive_metadata(value) if value is not None else value

    @model_validator(mode="after")
    def coherent_measurements(self):
        if (
            self.capture_time
            and self.capture_date
            and self.capture_time != self.capture_date
        ):
            raise ValueError("capture_time and capture_date must agree")
        supplied_resolution = "resolution" in self.model_fields_set
        supplied_unit = "resolution_unit" in self.model_fields_set
        if supplied_resolution != supplied_unit:
            raise ValueError("resolution and resolution_unit must be updated together")
        return self


class DatasetFileOut(BaseModel):
    id: str
    filename: str
    file_type: str
    size_bytes: int
    storage_key: str | None
    storage_provider: str
    storage_uri: str | None
    object_area: str
    status: str
    mime_type: str | None
    download_url: str | None = None
    md5_hash: str | None = None
    sha256_hash: str | None = None
    confirmed_at: datetime | None = None
    created_at: datetime


class DatasetOut(BaseModel):
    id: str
    company_id: str
    workspace_id: str | None
    site_id: str | None
    asset_id: str | None
    mission_id: str | None
    name: str
    description: str | None = None
    source_tool: str | None
    data_type: str | None
    dataset_type: str
    provider: str | None
    source: str | None
    source_reference: str | None
    status: str
    sector: str | None = None
    capture_time: datetime | None = None
    capture_date: datetime | None = None
    crs: str | None
    resolution: float | None
    resolution_unit: str | None
    processing_level: str
    quality_status: str
    metadata: dict[str, Any]
    provenance: dict[str, Any]
    object_prefix: str | None
    storage_provider: str
    files: list[DatasetFileOut] = Field(default_factory=list)
    file_count: int = 0
    total_size_bytes: int = 0
    lifecycle_version: int
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class DatasetListResponse(BaseModel):
    datasets: list[DatasetOut]
    total: int
    page: int
    per_page: int


class PresignedUrlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, max_length=240)
    content_type: str | None = Field(default=None, max_length=150)
    size_bytes: int = Field(gt=0)
    object_area: ObjectArea | None = None


class PresignedUrlResponse(BaseModel):
    upload_url: str
    storage_key: str
    expires_in: int
    file_id: str
    storage_provider: str
    required_headers: dict[str, str] = Field(default_factory=dict)


__all__ = [
    "DatasetCreate",
    "DatasetFileOut",
    "DatasetListResponse",
    "DatasetOut",
    "DatasetStatus",
    "DatasetUpdate",
    "PresignedUrlRequest",
    "PresignedUrlResponse",
    "SourceTool",
]
