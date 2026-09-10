"""HTTP contracts for customer-visible and assigned intelligence actions."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.modules.actions.domain import ActionStatus


class ActionOut(BaseModel):
    id: str
    organization_id: str
    workspace_id: str | None
    asset_id: str
    source_observation_id: str | None
    source_rule: str
    source_rule_version: str
    priority: str
    title: str
    description: str
    status: str
    due_date: datetime | None
    assigned_to_user_id: str | None
    recommended_catalog_item_id: str | None
    recommendation_refs: list[dict[str, Any]]
    outcome: dict[str, Any]
    lifecycle_version: int
    completed_by_user_id: str | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ActionListOut(BaseModel):
    items: list[ActionOut]
    total: int


class ActionStatusUpdate(BaseModel):
    status: ActionStatus
    expected_version: int = Field(ge=1)
    outcome: dict[str, Any] = Field(default_factory=dict)


class ActionUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    assigned_to_user_id: str | None = Field(default=None, max_length=36)
    due_date: datetime | None = None

    @field_validator("due_date")
    @classmethod
    def reasonable_due_date(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.year > 2200:
            raise ValueError("due_date is outside the supported range")
        return value


__all__ = ["ActionListOut", "ActionOut", "ActionStatusUpdate", "ActionUpdate"]
