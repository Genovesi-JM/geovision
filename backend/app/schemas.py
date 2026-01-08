"""Pydantic schemas for request/response models."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


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
    org_name: Optional[str] = None
    modules_enabled: List[str] = Field(default_factory=list)
    created_at: datetime

    model_config = {"from_attributes": True}


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)

    full_name: Optional[str] = None
    entity_type: str = Field(default="individual")
    org_name: Optional[str] = None

    account_name: Optional[str] = None
    sector_focus: str = Field(default="agro")
    modules_enabled: Optional[List[str]] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: EmailStr
    role: str

    model_config = {"from_attributes": True}


class AccountOut(BaseModel):
    id: str
    name: str
    sector_focus: str

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
    account: Optional[AccountOut] = None


class AccountCreate(BaseModel):
    name: str
    sector_focus: str
    entity_type: str = Field(default="org")
    org_name: Optional[str] = None
    modules_enabled: Optional[List[str]] = None


class AccountPublic(BaseModel):
    id: str
    name: str
    sector_focus: str
    entity_type: str
    org_name: Optional[str] = None
    modules_enabled: List[str] = Field(default_factory=list)
    role: Optional[str] = None

    model_config = {"from_attributes": True}


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
    status: Optional[str] = None
    trend: Optional[str] = None
    updated_at: datetime


class KPIResponse(BaseModel):
    items: List[KPIItem]
