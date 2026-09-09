"""Transport schemas for canonical organizations and workspaces."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.modules.organizations.domain import (
    CustomerRole,
    MembershipStatus,
)


DEFAULT_MODULES = ["kpi", "projects", "store", "alerts"]


def _json_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return []
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    return []


def _validate_timezone(value: str) -> str:
    timezone = value.strip()
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("timezone must be a valid IANA timezone") from exc
    return timezone


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    sector_focus: str = Field(default="agro", min_length=2, max_length=50)
    sectors: Optional[list[str]] = None
    entity_type: str = Field(default="org", min_length=2, max_length=50)
    customer_type: str = Field(default="business", min_length=2, max_length=50)
    use_cases: list[str] = Field(default_factory=list)
    modules_enabled: list[str] = Field(default_factory=lambda: list(DEFAULT_MODULES))


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    organization_type: str = Field(default="customer", min_length=2, max_length=50)
    country: str = Field(default="Angola", min_length=2, max_length=100)
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    workspace: WorkspaceCreate

    _timezone = field_validator("timezone")(_validate_timezone)


class WorkspaceOut(BaseModel):
    id: str
    organization_id: str
    name: str
    sector_focus: str
    entity_type: str
    customer_type: str
    dashboard_profile: str
    use_cases: list[str] = Field(default_factory=list)
    modules_enabled: list[str] = Field(default_factory=list)
    status: str
    role: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    _parse_use_cases = field_validator("use_cases", mode="before")(_json_list)
    _parse_modules = field_validator("modules_enabled", mode="before")(_json_list)


class OrganizationOut(BaseModel):
    id: str
    name: str
    organization_type: str
    country: str
    timezone: str
    status: str
    role: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    workspaces: list[WorkspaceOut] = Field(default_factory=list)


class MembershipOut(BaseModel):
    id: str
    organization_id: str
    user_id: Optional[str] = None
    email: EmailStr
    name: Optional[str] = None
    role: CustomerRole
    status: MembershipStatus
    invited_by_user_id: Optional[str] = None
    invited_at: Optional[datetime] = None
    joined_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class MembershipCreate(BaseModel):
    email: EmailStr
    user_id: Optional[str] = None
    name: Optional[str] = Field(default=None, max_length=200)
    role: CustomerRole = CustomerRole.MEMBER


class MembershipUpdate(BaseModel):
    role: Optional[CustomerRole] = None
    status: Optional[MembershipStatus] = None

    @model_validator(mode="after")
    def require_change(self):
        if self.role is None and self.status is None:
            raise ValueError("role or status is required")
        return self


class WorkspaceContextRequest(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=36)


class WorkspaceContextOut(BaseModel):
    user_id: str
    identity_subject: str
    active_workspace_id: Optional[str]
    active_organization_id: Optional[str]
    workspace_role: Optional[str]
    organization_role: Optional[str]
    internal_roles: list[str]
    permissions: list[str]


__all__ = [
    "DEFAULT_MODULES",
    "MembershipCreate",
    "MembershipOut",
    "MembershipUpdate",
    "OrganizationCreate",
    "OrganizationOut",
    "WorkspaceContextOut",
    "WorkspaceContextRequest",
    "WorkspaceCreate",
    "WorkspaceOut",
]
