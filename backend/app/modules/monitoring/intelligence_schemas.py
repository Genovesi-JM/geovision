"""HTTP-neutral validation and response contracts for remote intelligence."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.datasets.domain import reject_sensitive_metadata
from app.modules.monitoring.intelligence_domain import (
    IntelligenceKind,
    IntelligenceScheduleStatus,
    provider_code,
)


class SatelliteIntelligenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(min_length=1, max_length=36)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    lookback_days: int | None = Field(default=None, ge=1, le=366)
    collection: str | None = Field(default=None, min_length=2, max_length=120)
    max_cloud_cover_percent: float | None = Field(default=None, ge=0, le=100)
    limit: int | None = Field(default=None, ge=1, le=100)
    download_asset_keys: list[str] = Field(default_factory=list, max_length=20)
    force_refresh: bool = False

    @field_validator("download_asset_keys")
    @classmethod
    def stable_asset_keys(cls, value: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(item.strip() for item in value if item.strip()))
        if any(len(item) > 120 for item in normalized):
            raise ValueError("satellite asset keys must not exceed 120 characters")
        return normalized

    @model_validator(mode="after")
    def coherent_range(self):
        if self.starts_at and self.ends_at and self.starts_at > self.ends_at:
            raise ValueError("starts_at must not be after ends_at")
        if self.starts_at and self.lookback_days is not None:
            raise ValueError("lookback_days cannot be combined with starts_at")
        return self


class WeatherIntelligenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(min_length=1, max_length=36)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    lookback_hours: int | None = Field(default=None, ge=1, le=168)
    max_distance_km: float | None = Field(default=None, gt=0, le=1000)
    force_refresh: bool = False

    @model_validator(mode="after")
    def coherent_range(self):
        if self.starts_at and self.ends_at and self.starts_at > self.ends_at:
            raise ValueError("starts_at must not be after ends_at")
        if self.starts_at and self.lookback_hours is not None:
            raise ValueError("lookback_hours cannot be combined with starts_at")
        return self


class IntelligenceScheduleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(min_length=1, max_length=36)
    kind: IntelligenceKind
    provider: str | None = Field(default=None, max_length=80)
    cadence_minutes: int = Field(default=10080, ge=60, le=525600)
    lookback_days: int = Field(default=14, ge=1, le=366)
    options: dict[str, Any] = Field(default_factory=dict)
    next_run_at: datetime | None = None
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=200)

    @field_validator("provider", mode="before")
    @classmethod
    def stable_provider(cls, value: str | None) -> str | None:
        return provider_code(value) if value else None

    @field_validator("options")
    @classmethod
    def safe_options(cls, value: dict[str, Any]) -> dict[str, Any]:
        reject_sensitive_metadata(value, "options")
        return value


class IntelligenceScheduleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: IntelligenceScheduleStatus | None = None
    cadence_minutes: int | None = Field(default=None, ge=60, le=525600)
    lookback_days: int | None = Field(default=None, ge=1, le=366)
    options: dict[str, Any] | None = None
    next_run_at: datetime | None = None
    expected_version: int = Field(ge=1)

    @field_validator("options")
    @classmethod
    def safe_options(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is not None:
            reject_sensitive_metadata(value, "options")
        return value


class IntelligenceAcquisitionOut(BaseModel):
    id: str
    organization_id: str
    workspace_id: str | None
    asset_id: str
    schedule_id: str | None
    acquisition_id: str | None
    kind: str
    provider: str
    status: str
    cache_hit: bool = False
    cache_expires_at: datetime | None
    attempts: int
    max_attempts: int
    dataset_ids: list[str]
    summary: dict[str, Any]
    error_code: str | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None


class SatelliteSceneOut(BaseModel):
    id: str
    dataset_id: str
    provider: str
    provider_reference: str
    collection: str
    acquired_at: datetime
    published_at: datetime | None
    cloud_cover_percent: float | None
    resolution_meters: float | None
    crs: str | None
    bands: list[str]
    bbox: list[float]
    coverage: dict[str, Any] | None
    assets: dict[str, Any]
    provenance: dict[str, Any]
    source_link: str | None


class WeatherObservationOut(BaseModel):
    id: str
    dataset_id: str
    provider: str
    source_reference: str
    source_name: str | None
    observed_at: datetime
    metric: str
    value: float
    unit: str
    quality: str
    latitude: float | None
    longitude: float | None
    distance_km: float | None
    provenance: dict[str, Any]


class SatelliteIntelligenceOut(BaseModel):
    acquisition: IntelligenceAcquisitionOut
    scenes: list[SatelliteSceneOut]


class WeatherIntelligenceOut(BaseModel):
    acquisition: IntelligenceAcquisitionOut
    observations: list[WeatherObservationOut]


class IntelligenceScheduleOut(BaseModel):
    id: str
    organization_id: str
    workspace_id: str | None
    asset_id: str
    kind: str
    provider: str
    cadence_minutes: int
    lookback_days: int
    options: dict[str, Any]
    status: str
    next_run_at: datetime
    last_run_at: datetime | None
    last_success_at: datetime | None
    last_error_code: str | None
    last_error_message: str | None
    consecutive_failures: int
    lifecycle_version: int
    created_at: datetime
    updated_at: datetime


__all__ = [
    "IntelligenceAcquisitionOut",
    "IntelligenceScheduleCreate",
    "IntelligenceScheduleOut",
    "IntelligenceScheduleUpdate",
    "SatelliteIntelligenceOut",
    "SatelliteIntelligenceRequest",
    "SatelliteSceneOut",
    "WeatherIntelligenceOut",
    "WeatherIntelligenceRequest",
    "WeatherObservationOut",
]
