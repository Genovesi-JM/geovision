"""Transport contracts for fulfilment jobs and customer-safe progress."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.operations.domain import JobPriority, JobState, normalize_code, reject_sensitive_keys


class JobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str = Field(min_length=1, max_length=36)
    order_item_id: str | None = Field(default=None, max_length=36)
    asset_id: str | None = Field(default=None, max_length=36)
    job_type: str = Field(min_length=2, max_length=80)
    title: str = Field(min_length=2, max_length=200)
    priority: JobPriority = JobPriority.NORMAL
    requirements: dict[str, Any] = Field(default_factory=dict)
    direct_cost_amount: int | None = Field(default=None, ge=0)
    cost_currency: str | None = Field(default=None, min_length=3, max_length=5)
    cost_reference: str | None = Field(default=None, max_length=160)

    @field_validator("job_type")
    @classmethod
    def normalize_type(cls, value: str) -> str:
        return normalize_code(value, "CUSTOM_JOB")

    @field_validator("cost_currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value

    @field_validator("requirements")
    @classmethod
    def no_credentials(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_sensitive_keys(value)

    @model_validator(mode="after")
    def cost_has_currency(self):
        if self.direct_cost_amount is not None and not self.cost_currency:
            raise ValueError("cost_currency is required when direct_cost_amount is supplied")
        return self


class JobAssignmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contractor_id: str | None = Field(default=None, max_length=36)
    user_id: str | None = Field(default=None, max_length=36)
    clear_assignment: bool = False
    expected_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def one_target(self):
        target_count = int(self.contractor_id is not None) + int(self.user_id is not None)
        if self.clear_assignment and target_count:
            raise ValueError("clear_assignment cannot be combined with an assignee")
        if not self.clear_assignment and target_count != 1:
            raise ValueError("exactly one contractor_id or user_id is required")
        return self


class JobScheduleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    clear_schedule: bool = False
    expected_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def valid_window(self):
        if self.clear_schedule:
            if self.scheduled_start is not None or self.scheduled_end is not None:
                raise ValueError("clear_schedule cannot be combined with a schedule")
            return self
        if self.scheduled_start is None or self.scheduled_end is None:
            raise ValueError("scheduled_start and scheduled_end are both required")
        if self.scheduled_end <= self.scheduled_start:
            raise ValueError("scheduled_end must be after scheduled_start")
        return self


class JobStateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: JobState
    reason: str | None = Field(default=None, max_length=2_000)
    expected_version: int | None = Field(default=None, ge=1)


class JobDependencyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    depends_on_job_id: str = Field(min_length=1, max_length=36)


class JobDependencyOut(BaseModel):
    job_id: str
    job_number: str
    job_type: str
    state: str


class JobRestrictedOut(BaseModel):
    id: str
    job_number: str
    title: str
    job_type: str
    priority: str
    state: str
    scheduled_start: str | None
    scheduled_end: str | None
    actual_start: str | None
    completed_at: str | None
    requirements: dict[str, Any]
    lifecycle_version: int
    created_at: str
    updated_at: str


class JobInternalOut(JobRestrictedOut):
    order_id: str
    order_item_id: str | None
    asset_id: str | None
    assigned_contractor_id: str | None
    assigned_user_id: str | None
    direct_cost_amount: int | None
    cost_currency: str | None
    cost_reference: str | None
    plan_key: str | None
    resume_state: str | None
    dependencies: list[JobDependencyOut]


class JobPlanOut(BaseModel):
    order_id: str
    created_count: int
    existing_count: int
    jobs: list[JobInternalOut]


class CustomerJobStepOut(BaseModel):
    job_type: str
    status: str
    scheduled_start: str | None
    scheduled_end: str | None


class CustomerOrderProgressOut(BaseModel):
    order_id: str
    order_number: str | None
    status: str
    progress_percent: int
    total_steps: int
    completed_steps: int
    steps: list[CustomerJobStepOut]
    updated_at: str


__all__ = [
    "CustomerOrderProgressOut",
    "JobAssignmentUpdate",
    "JobCreate",
    "JobDependencyCreate",
    "JobInternalOut",
    "JobPlanOut",
    "JobRestrictedOut",
    "JobScheduleUpdate",
    "JobStateUpdate",
]
