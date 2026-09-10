"""Strict HTTP contracts for notification inboxes, preferences, and endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .domain import (
    NotificationCategory,
    NotificationEndpointPlatform,
    NotificationSeverity,
)


class NotificationOut(BaseModel):
    id: str
    organization_id: str
    workspace_id: str | None
    category: str
    notification_type: str
    title: str
    body: str
    severity: str
    target_type: str
    target_id: str | None
    occurrence_count: int
    first_occurred_at: datetime
    last_occurred_at: datetime
    read_at: datetime | None
    created_at: datetime
    updated_at: datetime


class NotificationListOut(BaseModel):
    items: list[NotificationOut]
    total: int
    unread: int


class UnreadCountOut(BaseModel):
    unread: int


class NotificationTargetOut(BaseModel):
    notification_id: str
    target_type: str
    target_id: str
    workspace_id: str | None
    app_path: str
    portal_path: str


class MarkAllReadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: str | None = Field(default=None, min_length=1, max_length=36)


class NotificationPreferenceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: str | None = Field(default=None, min_length=1, max_length=36)
    category: NotificationCategory
    in_app_enabled: bool = True
    push_enabled: bool = True
    email_enabled: bool = True
    sms_enabled: bool = False
    minimum_severity: NotificationSeverity = NotificationSeverity.INFO
    quiet_hours_start: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    quiet_hours_end: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    timezone: str = Field(default="UTC", min_length=1, max_length=64)

    @model_validator(mode="after")
    def complete_quiet_hours(self) -> "NotificationPreferenceUpdate":
        if (self.quiet_hours_start is None) != (self.quiet_hours_end is None):
            raise ValueError("quiet-hours start and end must be supplied together")
        return self

    @field_validator("timezone")
    @classmethod
    def clean_timezone(cls, value: str) -> str:
        return value.strip()


class NotificationPreferenceOut(NotificationPreferenceUpdate):
    id: str
    scope_key: str
    created_at: datetime
    updated_at: datetime


class NotificationPreferencesOut(BaseModel):
    items: list[NotificationPreferenceOut]


class NotificationEndpointUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: NotificationEndpointPlatform
    provider: str = Field(min_length=1, max_length=40)
    handle: str = Field(min_length=16, max_length=4096)
    organization_id: str | None = Field(default=None, min_length=1, max_length=36)
    expected_lifecycle_version: int | None = Field(default=None, ge=1)

    @field_validator("provider", "handle")
    @classmethod
    def clean_strings(cls, value: str) -> str:
        return value.strip()


class NotificationEndpointOut(BaseModel):
    id: str
    organization_id: str | None
    installation_id: str
    platform: str
    provider: str
    status: str
    last_seen_at: datetime
    lifecycle_version: int
    created_at: datetime
    updated_at: datetime


class NotificationEndpointDeleteOut(BaseModel):
    installation_id: str
    revoked: bool


class NotificationMaterializationOut(BaseModel):
    notification_ids: list[str]
    created: int
    aggregated: int
    suppressed: int
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "MarkAllReadRequest",
    "NotificationEndpointDeleteOut",
    "NotificationEndpointOut",
    "NotificationEndpointUpsert",
    "NotificationListOut",
    "NotificationMaterializationOut",
    "NotificationOut",
    "NotificationPreferenceOut",
    "NotificationPreferencesOut",
    "NotificationPreferenceUpdate",
    "NotificationTargetOut",
    "UnreadCountOut",
]
