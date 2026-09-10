"""Transport contracts for private operations resources and scoped assignments."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.operations.domain import (
    AssignmentStatus,
    ContractorAvailability,
    ContractorStatus,
    ServiceRequestStatus,
    reject_sensitive_keys,
)


class CapabilityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=2, max_length=200)
    category: str = Field(min_length=2, max_length=50)
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def no_credentials(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_sensitive_keys(value)


class CapabilityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=200)
    category: str | None = Field(default=None, min_length=2, max_length=50)
    description: str | None = None
    is_active: bool | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("metadata")
    @classmethod
    def no_credentials(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return reject_sensitive_keys(value) if value is not None else None


class CapabilityOut(BaseModel):
    id: str
    code: str
    name: str
    category: str
    description: str | None
    is_active: bool
    metadata: dict[str, Any]
    created_at: str
    updated_at: str


class ContractorCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=2, max_length=80)
    user_id: str | None = Field(default=None, max_length=36)
    display_name: str = Field(min_length=2, max_length=200)
    legal_name: str | None = Field(default=None, max_length=200)
    resource_type: str = Field(min_length=2, max_length=50)
    status: ContractorStatus = ContractorStatus.ACTIVE
    availability: ContractorAvailability = ContractorAvailability.AVAILABLE
    contact_email: str | None = Field(default=None, max_length=320)
    contact_phone: str | None = Field(default=None, max_length=50)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    region: str | None = Field(default=None, max_length=120)
    service_area: list[str | dict[str, Any]] = Field(default_factory=list, max_length=100)
    certifications: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    insurance: dict[str, Any] = Field(default_factory=dict)
    equipment: list[dict[str, Any]] = Field(default_factory=list, max_length=200)
    document_refs: list[dict[str, Any]] = Field(default_factory=list, max_length=200)
    quality_score: float | None = Field(default=None, ge=0, le=100)
    internal_notes: str | None = Field(default=None, max_length=10_000)
    capability_codes: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("country_code")
    @classmethod
    def normalize_country(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value

    @field_validator("resource_type")
    @classmethod
    def normalize_resource_type(cls, value: str) -> str:
        return value.strip().upper().replace(" ", "_")

    @field_validator("capability_codes")
    @classmethod
    def normalize_capabilities(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip().upper() for value in values if value.strip()))

    @field_validator(
        "service_area", "certifications", "insurance", "equipment", "document_refs"
    )
    @classmethod
    def no_credentials(cls, value: Any) -> Any:
        return reject_sensitive_keys(value)


class ContractorUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str | None = Field(default=None, max_length=36)
    display_name: str | None = Field(default=None, min_length=2, max_length=200)
    legal_name: str | None = Field(default=None, max_length=200)
    resource_type: str | None = Field(default=None, min_length=2, max_length=50)
    status: ContractorStatus | None = None
    availability: ContractorAvailability | None = None
    contact_email: str | None = Field(default=None, max_length=320)
    contact_phone: str | None = Field(default=None, max_length=50)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    region: str | None = Field(default=None, max_length=120)
    service_area: list[str | dict[str, Any]] | None = Field(default=None, max_length=100)
    certifications: list[dict[str, Any]] | None = Field(default=None, max_length=100)
    insurance: dict[str, Any] | None = None
    equipment: list[dict[str, Any]] | None = Field(default=None, max_length=200)
    document_refs: list[dict[str, Any]] | None = Field(default=None, max_length=200)
    quality_score: float | None = Field(default=None, ge=0, le=100)
    internal_notes: str | None = Field(default=None, max_length=10_000)
    capability_codes: list[str] | None = Field(default=None, max_length=100)

    @field_validator("country_code")
    @classmethod
    def normalize_country(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value

    @field_validator("resource_type")
    @classmethod
    def normalize_resource_type(cls, value: str | None) -> str | None:
        return value.strip().upper().replace(" ", "_") if value else value

    @field_validator("capability_codes")
    @classmethod
    def normalize_capabilities(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        return list(dict.fromkeys(value.strip().upper() for value in values if value.strip()))

    @field_validator(
        "service_area", "certifications", "insurance", "equipment", "document_refs"
    )
    @classmethod
    def no_credentials(cls, value: Any) -> Any:
        return reject_sensitive_keys(value) if value is not None else value


class ContractorInternalOut(BaseModel):
    id: str
    code: str
    user_id: str | None
    display_name: str
    legal_name: str | None
    resource_type: str
    status: str
    availability: str
    contact_email: str | None
    contact_phone: str | None
    country_code: str | None
    region: str | None
    service_area: list[Any]
    certifications: list[dict[str, Any]]
    insurance: dict[str, Any]
    equipment: list[dict[str, Any]]
    document_refs: list[dict[str, Any]]
    quality_score: float | None
    internal_notes: str | None
    capabilities: list[dict[str, Any]]
    created_at: str
    updated_at: str


class ContractorSelfProfileOut(BaseModel):
    id: str
    display_name: str
    resource_type: str
    status: str
    availability: str
    contact_email: str | None
    contact_phone: str | None
    country_code: str | None
    region: str | None
    service_area: list[Any]
    certifications: list[dict[str, Any]]
    equipment: list[dict[str, Any]]
    document_refs: list[dict[str, Any]]
    capabilities: list[dict[str, Any]]


class ContractorSelfUpdate(BaseModel):
    """Fields a contractor may maintain without changing staff-owned vetting."""

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=2, max_length=200)
    availability: ContractorAvailability | None = None
    contact_email: str | None = Field(default=None, max_length=320)
    contact_phone: str | None = Field(default=None, max_length=50)
    region: str | None = Field(default=None, max_length=120)
    service_area: list[str | dict[str, Any]] | None = Field(
        default=None, max_length=100
    )
    equipment: list[dict[str, Any]] | None = Field(default=None, max_length=200)

    @field_validator("service_area", "equipment")
    @classmethod
    def no_credentials(cls, value: Any) -> Any:
        return reject_sensitive_keys(value) if value is not None else value


class AssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contractor_id: str = Field(max_length=36)
    order_id: str | None = Field(default=None, max_length=36)
    fulfilment_job_id: str | None = Field(default=None, max_length=36)
    title: str = Field(min_length=2, max_length=200)
    location: dict[str, Any] = Field(default_factory=dict)
    window_start: datetime | None = None
    window_end: datetime | None = None
    requirements: dict[str, Any] = Field(default_factory=dict)
    upload_area: dict[str, Any] = Field(default_factory=dict)
    required_documents: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    agreed_cost_amount: int | None = Field(default=None, ge=0)
    cost_currency: str | None = Field(default=None, min_length=3, max_length=5)
    internal_notes: str | None = Field(default=None, max_length=10_000)

    @field_validator("cost_currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value

    @field_validator("location", "requirements", "upload_area", "required_documents")
    @classmethod
    def no_credentials(cls, value: Any) -> Any:
        return reject_sensitive_keys(value)

    @model_validator(mode="after")
    def valid_window(self):
        if self.window_start and self.window_end and self.window_end <= self.window_start:
            raise ValueError("window_end must be after window_start")
        if self.agreed_cost_amount is not None and not self.cost_currency:
            raise ValueError("cost_currency is required when an agreed cost is supplied")
        return self


class AssignmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AssignmentStatus | None = None
    title: str | None = Field(default=None, min_length=2, max_length=200)
    location: dict[str, Any] | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    requirements: dict[str, Any] | None = None
    upload_area: dict[str, Any] | None = None
    required_documents: list[dict[str, Any]] | None = Field(default=None, max_length=100)
    agreed_cost_amount: int | None = Field(default=None, ge=0)
    cost_currency: str | None = Field(default=None, min_length=3, max_length=5)
    internal_notes: str | None = Field(default=None, max_length=10_000)
    expected_version: int | None = Field(default=None, ge=1)

    @field_validator("cost_currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value

    @field_validator("location", "requirements", "upload_area", "required_documents")
    @classmethod
    def no_credentials(cls, value: Any) -> Any:
        return reject_sensitive_keys(value) if value is not None else value


class AssignmentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["ACCEPTED", "DECLINED"]
    expected_version: int | None = Field(default=None, ge=1)


class AssignmentRestrictedOut(BaseModel):
    id: str
    assignment_number: str
    title: str
    status: str
    location: dict[str, Any]
    window_start: str | None
    window_end: str | None
    requirements: dict[str, Any]
    upload_area: dict[str, Any]
    required_documents: list[dict[str, Any]]
    document_profile: list[dict[str, Any]]
    lifecycle_version: int
    created_at: str
    updated_at: str


class AssignmentInternalOut(AssignmentRestrictedOut):
    contractor_id: str
    order_id: str | None
    fulfilment_job_id: str | None
    agreed_cost_amount: int | None
    cost_currency: str | None
    internal_notes: str | None
    assigned_by_user_id: str | None


class ServiceRequestLinkUpdate(BaseModel):
    """Internal, tenant-bound progress and durable-link update."""

    model_config = ConfigDict(extra="forbid")

    organization_id: str = Field(min_length=1, max_length=36)
    workspace_id: str = Field(min_length=1, max_length=36)
    asset_id: str | None = Field(default=None, max_length=36)
    order_id: str | None = Field(default=None, max_length=36)
    report_id: str | None = Field(default=None, max_length=36)
    status: ServiceRequestStatus | None = None
    progress_percent: int | None = Field(default=None, ge=0, le=100)
    assigned_team: str | None = Field(default=None, max_length=200)
    expected_version: int = Field(ge=1)

    @model_validator(mode="after")
    def has_change(self):
        scope_fields = {"organization_id", "workspace_id", "expected_version"}
        if not self.model_fields_set.difference(scope_fields):
            raise ValueError("At least one service-request field must be updated")
        if "progress_percent" in self.model_fields_set and self.progress_percent is None:
            raise ValueError("progress_percent cannot be null")
        return self


class ServiceRequestLinkOut(BaseModel):
    id: str
    organization_id: str
    workspace_id: str
    user_id: str
    site_id: str | None
    asset_id: str | None
    order_id: str | None
    report_id: str | None
    status: str
    progress_percent: int
    assigned_team: str | None
    lifecycle_version: int
    created_at: datetime
    updated_at: datetime


__all__ = [
    "AssignmentCreate",
    "AssignmentDecision",
    "AssignmentInternalOut",
    "AssignmentRestrictedOut",
    "AssignmentUpdate",
    "CapabilityCreate",
    "CapabilityOut",
    "CapabilityUpdate",
    "ContractorCreate",
    "ContractorInternalOut",
    "ContractorSelfProfileOut",
    "ContractorSelfUpdate",
    "ContractorUpdate",
    "ServiceRequestLinkOut",
    "ServiceRequestLinkUpdate",
]
