"""HTTP-neutral contracts for acquisitions and drone-specific extensions."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.missions.domain import (
    AcquisitionState,
    AcquisitionType,
    reject_sensitive_metadata,
)


class DroneDetailsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aircraft_id: str | None = Field(default=None, max_length=36)
    payload_reference: str | None = Field(default=None, max_length=200)
    operator_user_id: str | None = Field(default=None, max_length=36)
    contractor_id: str | None = Field(default=None, max_length=36)
    mission_requirements: dict[str, Any] = Field(default_factory=dict)
    capture_area: dict[str, Any] | None = None
    flight_metadata: dict[str, Any] = Field(default_factory=dict)
    reflight_of_acquisition_id: str | None = Field(default=None, max_length=36)
    reflight_reason: str | None = Field(default=None, max_length=2_000)

    @field_validator("mission_requirements", "capture_area", "flight_metadata")
    @classmethod
    def no_credentials(cls, value: Any) -> Any:
        return reject_sensitive_metadata(value) if value is not None else value

    @model_validator(mode="after")
    def one_operator(self):
        if self.operator_user_id and self.contractor_id:
            raise ValueError("Use an internal operator or a contractor, not both")
        if self.reflight_of_acquisition_id and not self.reflight_reason:
            raise ValueError("reflight_reason is required for a linked reflight")
        return self


class AcquisitionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(min_length=1, max_length=36)
    acquisition_type: AcquisitionType
    title: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    drone_details: DroneDetailsInput | None = None

    @field_validator("metadata")
    @classmethod
    def no_credentials(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_sensitive_metadata(value)

    @model_validator(mode="after")
    def modality_and_schedule(self):
        if self.acquisition_type is not AcquisitionType.DRONE and self.drone_details:
            raise ValueError("drone_details are valid only for DRONE acquisitions")
        if (self.scheduled_start is None) != (self.scheduled_end is None):
            raise ValueError("scheduled_start and scheduled_end must be supplied together")
        if (
            self.scheduled_start
            and self.scheduled_end
            and self.scheduled_end <= self.scheduled_start
        ):
            raise ValueError("scheduled_end must be after scheduled_start")
        return self


class InternalAcquisitionCreate(AcquisitionCreate):
    order_id: str | None = Field(default=None, max_length=36)
    fulfilment_job_id: str | None = Field(default=None, max_length=36)
    provider_code: str | None = Field(default=None, max_length=80)
    provider_reference: str | None = Field(default=None, max_length=200)
    provenance: dict[str, Any] = Field(default_factory=dict)
    output_refs: list[dict[str, Any]] = Field(default_factory=list, max_length=500)

    @field_validator("provenance", "output_refs")
    @classmethod
    def safe_internal_metadata(cls, value: Any) -> Any:
        return reject_sensitive_metadata(value)


class AcquisitionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    metadata: dict[str, Any] | None = None
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    clear_schedule: bool = False
    expected_version: int | None = Field(default=None, ge=1)

    @field_validator("metadata")
    @classmethod
    def no_credentials(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return reject_sensitive_metadata(value) if value is not None else value

    @model_validator(mode="after")
    def valid_schedule(self):
        if self.clear_schedule and (
            self.scheduled_start is not None or self.scheduled_end is not None
        ):
            raise ValueError("clear_schedule cannot be combined with schedule values")
        supplied = self.scheduled_start is not None or self.scheduled_end is not None
        if supplied and (self.scheduled_start is None or self.scheduled_end is None):
            raise ValueError("scheduled_start and scheduled_end must be supplied together")
        if (
            self.scheduled_start
            and self.scheduled_end
            and self.scheduled_end <= self.scheduled_start
        ):
            raise ValueError("scheduled_end must be after scheduled_start")
        return self


class InternalAcquisitionUpdate(AcquisitionUpdate):
    provider_code: str | None = Field(default=None, max_length=80)
    provider_reference: str | None = Field(default=None, max_length=200)
    provenance: dict[str, Any] | None = None
    output_refs: list[dict[str, Any]] | None = Field(default=None, max_length=500)
    drone_details: DroneDetailsInput | None = None

    @field_validator("provenance", "output_refs")
    @classmethod
    def safe_internal_metadata(cls, value: Any) -> Any:
        return reject_sensitive_metadata(value) if value is not None else value


class AcquisitionStateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: AcquisitionState
    reason: str | None = Field(default=None, max_length=2_000)
    expected_version: int | None = Field(default=None, ge=1)


class CustomerDroneDetailsOut(BaseModel):
    aircraft_id: str | None
    payload_reference: str | None
    mission_requirements: dict[str, Any]
    capture_area: dict[str, Any] | None
    flight_metadata: dict[str, Any]
    reflight_of_acquisition_id: str | None
    reflight_reason: str | None


class InternalDroneDetailsOut(CustomerDroneDetailsOut):
    operator_user_id: str | None
    contractor_id: str | None


class AcquisitionOut(BaseModel):
    id: str
    acquisition_number: str
    asset_id: str
    acquisition_type: str
    title: str
    description: str | None
    state: str
    metadata: dict[str, Any]
    output_refs: list[dict[str, Any]]
    scheduled_start: str | None
    scheduled_end: str | None
    started_at: str | None
    captured_at: str | None
    completed_at: str | None
    lifecycle_version: int
    drone_details: CustomerDroneDetailsOut | None
    created_at: str
    updated_at: str


class InternalAcquisitionOut(AcquisitionOut):
    organization_id: str
    workspace_id: str | None
    order_id: str | None
    fulfilment_job_id: str | None
    provider_code: str | None
    provider_reference: str | None
    provenance: dict[str, Any]
    legacy_source: str | None
    legacy_source_id: str | None
    created_by_user_id: str | None
    updated_by_user_id: str | None
    drone_details: InternalDroneDetailsOut | None


__all__ = [
    "AcquisitionCreate",
    "AcquisitionOut",
    "AcquisitionStateUpdate",
    "AcquisitionUpdate",
    "DroneDetailsInput",
    "InternalAcquisitionCreate",
    "InternalAcquisitionOut",
    "InternalAcquisitionUpdate",
]
