"""Stable read contracts for the customer web portal.

The portal consumes customer-safe projections only.  These contracts never
expose internal Operations resources, provider credentials, or provider IDs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


PortalCapability = Literal[
    "overview",
    "assets",
    "actions",
    "monitoring",
    "services",
    "map",
    "analytics",
    "reports",
    "catalog",
    "orders",
    "billing",
    "team",
    "integrations",
    "settings",
]
PortalNavigationGroup = Literal[
    "overview",
    "operations",
    "intelligence",
    "commercial",
    "management",
]
PortalTargetType = Literal[
    "WORKSPACE",
    "ASSET",
    "ACTION",
    "SERVICE",
    "SERVICE_RESULT",
    "ORDER",
    "REPORT",
]


class PortalWorkspaceOut(BaseModel):
    id: str
    organization_id: str
    name: str
    organization_name: str
    role: str
    sector: str
    modules_enabled: list[str] = Field(default_factory=list)


class PortalSubscriptionOut(BaseModel):
    plan: str
    status: Literal["active", "expiring", "expired", "pending"]
    tier: str
    valid_until: datetime | None = None
    source: Literal["entitlement", "organization_plan"]


class PortalNavigationItemOut(BaseModel):
    key: PortalCapability
    label: str
    route: str
    capability: PortalCapability


class PortalNavigationGroupOut(BaseModel):
    key: PortalNavigationGroup
    label: str
    items: list[PortalNavigationItemOut] = Field(default_factory=list)


class PortalAssetTreeNodeOut(BaseModel):
    id: str
    parent_asset_id: str | None = None
    name: str
    sector: str
    asset_type: str
    status: str
    synthetic: bool = False
    synthetic_marker: str | None = None
    synthetic_notice: str | None = None
    source: str | None = None
    children: list["PortalAssetTreeNodeOut"] = Field(default_factory=list)


class PortalDestinationRuleOut(BaseModel):
    target_type: PortalTargetType
    route_template: str
    capability: PortalCapability


class PortalDeepLinkContractOut(BaseModel):
    version: Literal["geovision.portal-destination.v1"] = (
        "geovision.portal-destination.v1"
    )
    destinations: list[PortalDestinationRuleOut] = Field(default_factory=list)


class PortalExperienceOut(BaseModel):
    active_workspace_id: str
    active_organization_id: str
    organization_name: str
    active_workspace: PortalWorkspaceOut
    permissions: list[str] = Field(default_factory=list)
    capabilities: list[PortalCapability] = Field(default_factory=list)
    feature_flags: dict[PortalCapability, bool] = Field(default_factory=dict)
    subscription: PortalSubscriptionOut
    workspaces: list[PortalWorkspaceOut] = Field(default_factory=list)
    navigation: list[PortalNavigationGroupOut] = Field(default_factory=list)
    asset_tree: list[PortalAssetTreeNodeOut] = Field(default_factory=list)
    deep_link_contract: PortalDeepLinkContractOut


class PortalTargetOut(BaseModel):
    target_type: PortalTargetType
    target_id: str


class PortalKpiCardOut(BaseModel):
    key: str
    name: str
    value: float | int | str | None = None
    display_value: str
    unit: str | None = None
    status: str
    confidence: float | None = None
    measured_at: datetime | None = None
    change_percent: float | None = None
    synthetic: bool = False
    synthetic_marker: str | None = None
    synthetic_notice: str | None = None
    source: str | None = None


class PortalAssetSummaryItemOut(BaseModel):
    id: str
    parent_asset_id: str | None = None
    name: str
    sector: str
    asset_type: str
    status: str
    location_label: str | None = None
    center: dict[str, float] | None = None
    children_count: int = Field(default=0, ge=0)
    decision_status: str
    confidence: float | None = None
    measured_at: datetime | None = None
    primary_kpis: list[PortalKpiCardOut] = Field(default_factory=list)
    secondary_kpis: list[PortalKpiCardOut] = Field(default_factory=list)
    technical_metric_count: int = Field(default=0, ge=0)
    technical_metrics_path: str
    open_action_count: int = Field(default=0, ge=0)
    critical_observation_count: int = Field(default=0, ge=0)
    warning_observation_count: int = Field(default=0, ge=0)
    unvalidated_observation_count: int = Field(default=0, ge=0)
    latest_observation_at: datetime | None = None
    destination: PortalTargetOut
    synthetic: bool = False
    synthetic_marker: str | None = None
    synthetic_notice: str | None = None
    source: str | None = None


class PortalAssetTotalsOut(BaseModel):
    assets: int = Field(ge=0)
    active: int = Field(ge=0)
    attention: int = Field(ge=0)
    open_actions: int = Field(ge=0)
    published_reports: int = Field(ge=0)
    offline_devices: int = Field(ge=0)


class PortalAssetSummaryOut(BaseModel):
    workspace_id: str
    generated_at: datetime
    totals: PortalAssetTotalsOut
    items: list[PortalAssetSummaryItemOut] = Field(default_factory=list)


class PortalGeoJsonFeatureOut(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: str
    geometry: dict[str, Any]
    properties: dict[str, Any] = Field(default_factory=dict)


class PortalGeoJsonFeatureCollectionOut(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[PortalGeoJsonFeatureOut] = Field(default_factory=list)


class PortalMapLayerOut(BaseModel):
    id: Literal["assets", "observations", "devices"]
    label: str
    kind: Literal["ASSET", "OBSERVATION", "DEVICE"]
    default_visible: bool
    geometry_types: list[str] = Field(default_factory=list)
    feature_collection: PortalGeoJsonFeatureCollectionOut


class PortalMapLayersOut(BaseModel):
    workspace_id: str
    generated_at: datetime
    bounds: list[float] | None = None
    layers: list[PortalMapLayerOut] = Field(default_factory=list)


__all__ = [
    "PortalAssetSummaryOut",
    "PortalCapability",
    "PortalExperienceOut",
    "PortalMapLayersOut",
]
