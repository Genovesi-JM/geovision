"""Typed customer-mobile experience contracts.

These schemas intentionally expose product capabilities rather than internal
module names.  They are projections only; every destination continues to
enforce its own backend authorization rules.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.modules.actions.schemas import ActionOut


MobileCapability = Literal[
    "assets",
    "actions",
    "services",
    "reports",
    "devices",
    "team",
    "billing",
    "settings",
    "support",
]
MobileTargetType = Literal[
    "ACTION",
    "ASSET",
    "SERVICE",
    "SERVICE_RESULT",
    "ORDER",
    "REPORT",
]


class MobileWorkspaceOut(BaseModel):
    id: str
    organization_id: str
    name: str
    organization_name: str
    role: str
    sector: str
    sectors: list[str] = Field(default_factory=list)
    modules_enabled: list[str] = Field(default_factory=list)


class MobileExperienceOut(BaseModel):
    active_workspace_id: str | None
    active_organization_id: str | None
    permissions: list[str] = Field(default_factory=list)
    capabilities: list[MobileCapability] = Field(default_factory=list)
    workspaces: list[MobileWorkspaceOut] = Field(default_factory=list)


class MobileAttentionOut(BaseModel):
    critical: int = Field(ge=0)
    attention: int = Field(ge=0)
    scheduled: int = Field(ge=0)
    completed_recent: int = Field(ge=0)
    active_services: int = Field(ge=0)
    offline_devices: int = Field(ge=0)


class MobilePriorityItemOut(BaseModel):
    id: str
    target_type: MobileTargetType
    target_id: str
    title: str
    summary: str
    severity: str
    due_at: datetime | None = None


class MobileLatestResultOut(BaseModel):
    target_type: MobileTargetType
    target_id: str
    title: str
    summary: str
    completed_at: datetime


class MobileHomeOut(BaseModel):
    workspace_id: str
    organization_name: str
    workspace_name: str
    attention: MobileAttentionOut
    priority_items: list[MobilePriorityItemOut] = Field(default_factory=list)
    latest_result: MobileLatestResultOut | None = None
    updated_at: datetime


class MobileActionBucketsOut(BaseModel):
    critical: list[ActionOut] = Field(default_factory=list)
    attention: list[ActionOut] = Field(default_factory=list)
    scheduled: list[ActionOut] = Field(default_factory=list)
    completed: list[ActionOut] = Field(default_factory=list)


class MobileServiceResultOut(BaseModel):
    title: str
    summary: str
    report_id: str
    asset_id: str
    published_at: datetime


class MobileServiceRequestOut(BaseModel):
    id: str
    organization_id: str | None = None
    workspace_id: str | None = None
    asset_id: str | None = None
    order_id: str | None = None
    report_id: str | None = None
    site_id: str
    site_name: str
    type: str
    urgency: str
    description: str
    status: str
    progress_percent: int
    attachments: list[str] = Field(default_factory=list)
    assigned_team: str | None = None
    lifecycle_version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime
    result: MobileServiceResultOut | None = None


__all__ = [
    "MobileActionBucketsOut",
    "MobileAttentionOut",
    "MobileCapability",
    "MobileExperienceOut",
    "MobileHomeOut",
    "MobileLatestResultOut",
    "MobilePriorityItemOut",
    "MobileServiceRequestOut",
    "MobileServiceResultOut",
    "MobileTargetType",
    "MobileWorkspaceOut",
]
