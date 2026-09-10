"""Normalized frontend contracts for KPIs, observations, alerts, and summaries."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class KpiDefinitionOut(BaseModel):
    id: str
    sector: str
    key: str
    name: str
    unit: str | None
    description: str | None
    calculator: str
    calculator_version: str
    importance: str
    display_format: dict[str, Any]
    status_policy: dict[str, Any]


class AssetKpiOut(BaseModel):
    definition: KpiDefinitionOut
    availability: str
    current: float | int | str | None
    previous: float | int | str | None
    baseline: float | int | str | None
    change: float | None
    change_percent: float | None
    baseline_change: float | None
    baseline_change_percent: float | None
    display_value: str
    status: str
    confidence: float | None
    measured_at: datetime | None
    previous_measured_at: datetime | None
    baseline_measured_at: datetime | None
    source: str | None
    mission_id: str | None
    dataset_id: str | None
    provenance: dict[str, Any]


class AssetKpiListOut(BaseModel):
    asset_id: str
    items: list[AssetKpiOut]
    total: int


class ObservationOut(BaseModel):
    id: str
    organization_id: str
    workspace_id: str | None
    asset_id: str
    mission_id: str | None
    dataset_id: str | None
    type: str
    severity: str
    geometry: dict[str, Any] | None
    value: dict[str, Any]
    numeric_value: float | None
    unit: str | None
    metadata: dict[str, Any]
    confidence: float
    source: str
    algorithm: str
    algorithm_version: str
    provenance: dict[str, Any]
    validation_status: str
    validated_by_user_id: str | None
    validated_at: datetime | None
    detected_at: datetime
    created_at: datetime
    updated_at: datetime


class ObservationListOut(BaseModel):
    asset_id: str
    items: list[ObservationOut]
    total: int


class IntelligenceAlertOut(BaseModel):
    id: str
    asset_id: str
    observation_type: str
    severity: str
    validation_status: str
    confidence: float
    detected_at: datetime
    source: str
    algorithm_version: str


class IntelligenceAlertListOut(BaseModel):
    asset_id: str
    items: list[IntelligenceAlertOut]
    total: int
    critical_count: int
    warning_count: int
    unvalidated_count: int


class AssetIntelligenceSummaryOut(BaseModel):
    asset_id: str
    sector: str
    status: str
    confidence: float | None
    measured_at: datetime | None
    primary_kpis: list[AssetKpiOut]
    secondary_kpis: list[AssetKpiOut]
    technical_kpi_count: int
    open_action_count: int
    critical_observation_count: int
    warning_observation_count: int
    unvalidated_observation_count: int
    latest_observation_at: datetime | None


__all__ = [
    "AssetIntelligenceSummaryOut",
    "AssetKpiListOut",
    "AssetKpiOut",
    "IntelligenceAlertListOut",
    "IntelligenceAlertOut",
    "KpiDefinitionOut",
    "ObservationListOut",
    "ObservationOut",
]
