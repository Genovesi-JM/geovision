"""HTTP contracts for Mining/Quarry operational intelligence."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MiningEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: datetime | None = None


class MiningCapabilitiesOut(BaseModel):
    sector: str
    public_sector: str
    maturity: str
    enabled: bool
    algorithm_bundle_version: str
    analysis_schema: str
    asset_types: list[str]
    dataset_types: list[str]
    kpis: list[dict[str, Any]]
    map_layer_kinds: list[str]
    comparison_kinds: list[str]
    evidence_guardrails: list[str]


class MiningEvaluationOut(BaseModel):
    asset_id: str
    evaluated_at: datetime
    source_availability: dict[str, Any]
    evidence: dict[str, Any]
    kpi_value_ids: list[str]
    observation_ids: list[str]
    action_ids: list[str]
    kpis: list[dict[str, Any]]


class MiningComparisonsOut(BaseModel):
    asset_id: str
    items: list[dict[str, Any]]
    total: int


class MiningMapLayersOut(BaseModel):
    asset_id: str
    items: list[dict[str, Any]]
    total: int


class MiningReportContextOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    context_schema: str = Field(alias="schema", serialization_alias="schema")
    algorithm_bundle_version: str
    asset: dict[str, Any]
    as_of: datetime
    source_availability: dict[str, Any]
    evidence: dict[str, Any]
    kpis: list[dict[str, Any]]
    observations: list[dict[str, Any]]
    open_actions: list[dict[str, Any]]
    comparisons: list[dict[str, Any]]
    map_layers: list[dict[str, Any]]
    limitations: list[str]


__all__ = [
    "MiningCapabilitiesOut",
    "MiningComparisonsOut",
    "MiningEvaluationOut",
    "MiningEvaluationRequest",
    "MiningMapLayersOut",
    "MiningReportContextOut",
]
