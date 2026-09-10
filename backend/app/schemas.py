"""Pydantic schemas for request/response models."""

import json
from datetime import datetime
from typing import Annotated, List, Optional

from pydantic import BaseModel, EmailStr, Field, StringConstraints, field_validator

from .core.passwords import validate_new_password
from .sector_taxonomy import normalize_capability_modules, public_sector_focus


SectorSelectionValue = Annotated[str, StringConstraints(max_length=320)]


def _json_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def _module_list(value):
    return normalize_capability_modules(_json_list(value))


def _optional_module_list(value):
    return normalize_capability_modules(value) if value is not None else None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserSummary(BaseModel):
    id: str
    email: EmailStr
    role: str
    full_name: Optional[str] = None

    model_config = {"from_attributes": True}


class AccountSummary(BaseModel):
    id: str
    name: str
    sector_focus: str
    entity_type: str
    customer_type: str = "farm"
    dashboard_profile: str = "farm"
    use_cases: List[str] = Field(default_factory=list)
    org_name: Optional[str] = None
    modules_enabled: List[str] = Field(default_factory=list)
    created_at: datetime

    model_config = {"from_attributes": True}

    _parse_use_cases = field_validator("use_cases", mode="before")(_json_list)
    _normalize_modules = field_validator("modules_enabled", mode="before")(_module_list)
    _normalize_sector_focus = field_validator("sector_focus", mode="before")(
        public_sector_focus
    )


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)

    _validate_password = field_validator("password")(validate_new_password)

    full_name: Optional[str] = None
    entity_type: str = Field(default="individual")
    org_name: Optional[str] = None

    account_name: Optional[str] = None
    sector_focus: Optional[str] = Field(default=None, max_length=320)
    sectors: Optional[List[SectorSelectionValue]] = Field(default=None, max_length=6)
    customer_type: str = Field(default="farm")
    use_cases: Optional[List[str]] = None
    modules_enabled: Optional[List[str]] = None
    # New clients choose an outcome, not a customer/account taxonomy. When
    # omitted, the historical profile fields above remain fully compatible.
    intent: Optional[str] = Field(default=None, max_length=40)

    _normalize_modules = field_validator("modules_enabled", mode="before")(
        _optional_module_list
    )


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: EmailStr
    role: str
    name: Optional[str] = None

    model_config = {"from_attributes": True}


class AccountOut(BaseModel):
    id: str
    name: str
    sector_focus: str
    entity_type: str
    customer_type: str = "farm"
    dashboard_profile: str = "farm"
    use_cases: List[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}

    _parse_use_cases = field_validator("use_cases", mode="before")(_json_list)
    _normalize_sector_focus = field_validator("sector_focus", mode="before")(
        public_sector_focus
    )


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: Optional[str] = None
    user: UserOut
    account: Optional[AccountOut] = None


class AccountCreate(BaseModel):
    name: str
    sector_focus: str = Field(min_length=2, max_length=320)
    sectors: Optional[List[SectorSelectionValue]] = Field(default=None, max_length=6)
    entity_type: str = Field(default="org")
    customer_type: str = Field(default="business")
    use_cases: Optional[List[str]] = None
    org_name: Optional[str] = None
    modules_enabled: Optional[List[str]] = None

    _normalize_modules = field_validator("modules_enabled", mode="before")(
        _optional_module_list
    )


class AccountPublic(BaseModel):
    id: str
    name: str
    sector_focus: str
    entity_type: str
    customer_type: str = "farm"
    dashboard_profile: str = "farm"
    use_cases: List[str] = Field(default_factory=list)
    org_name: Optional[str] = None
    modules_enabled: List[str] = Field(default_factory=list)
    role: Optional[str] = None

    model_config = {"from_attributes": True}

    _parse_use_cases = field_validator("use_cases", mode="before")(_json_list)
    _normalize_modules = field_validator("modules_enabled", mode="before")(_module_list)
    _normalize_sector_focus = field_validator("sector_focus", mode="before")(
        public_sector_focus
    )


class ProjectCreate(BaseModel):
    project_type: str
    client_name: str
    location: Optional[str] = None


class ProjectOut(BaseModel):
    id: int
    project_type: str
    client_name: str
    location: Optional[str] = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AccountSwitchRequest(BaseModel):
    account_id: str


class ProfileOut(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    company: Optional[str] = None

    model_config = {"from_attributes": True}


class MeResponse(BaseModel):
    user: UserSummary
    profile: Optional[ProfileOut] = None
    accounts: List[AccountPublic]
    default_account_id: Optional[str] = None


class KPIItem(BaseModel):
    id: str
    label: str
    value: float | int | str
    unit: Optional[str] = None
    status: Optional[str] = None  # ok, warning, critical
    trend: Optional[str] = None  # up, down, stable
    updated_at: Optional[datetime] = None
    sector: Optional[str] = None  # For multi-sector filtering
    description: Optional[str] = None  # Human-readable explanation for chatbot


class KPIResponse(BaseModel):
    items: List[KPIItem]
    sector: Optional[str] = None  # Active sector filter


class AlertItem(BaseModel):
    id: str
    severity: str  # info, warning, critical
    sector: str
    title: str
    description: str
    location: Optional[str] = None
    created_at: datetime
    acknowledged: bool = False
    resolved: bool = False


class AlertsResponse(BaseModel):
    alerts: List[AlertItem]
    total: int
    critical_count: int
    warning_count: int
    availability: str = "NO_DATA"


class ServiceItem(BaseModel):
    id: str
    type: str
    location: str
    area_hectares: Optional[float] = None
    status: str  # planned, in_field, processing, completed
    sector: str
    progress_percent: Optional[int] = None
    updated_at: datetime


class HardwareItem(BaseModel):
    id: str
    name: str
    location: str
    status: str  # online, offline, maintenance
    sector: str
    last_reading_at: Optional[datetime] = None


class DashboardContext(BaseModel):
    """Structured context for chatbot to understand what user sees."""

    account_name: str
    sectors: List[str]
    active_sector: Optional[str] = None
    kpis: List[KPIItem]
    alerts: List[AlertItem]
    alerts_availability: str = "NO_DATA"
    services_count: Optional[int] = None
    hardware_count: Optional[int] = None
    summary_text: str  # Human-readable summary for chatbot
