"""HTTP-neutral request and response contracts for processing jobs."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.datasets.domain import reject_sensitive_metadata
from app.modules.processing.domain import normalize_output_type


class ProcessingJobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_dataset_ids: list[str] = Field(min_length=1, max_length=20)
    requested_outputs: list[str] = Field(min_length=1, max_length=8)
    provider: str | None = Field(default=None, max_length=80)
    fulfilment_job_id: str | None = Field(default=None, max_length=36)
    estimated_cost_amount: int | None = Field(default=None, ge=0)
    cost_currency: str = Field(default="USD", min_length=3, max_length=5)
    max_retries: int | None = Field(default=None, ge=0, le=20)
    options: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=200)

    @field_validator("source_dataset_ids")
    @classmethod
    def unique_sources(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item or len(item) > 36 for item in normalized):
            raise ValueError("source dataset IDs must be non-empty and at most 36 characters")
        if len(set(normalized)) != len(normalized):
            raise ValueError("source dataset IDs must be unique")
        return normalized

    @field_validator("requested_outputs")
    @classmethod
    def valid_outputs(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(normalize_output_type(item) for item in value))

    @field_validator("provider", mode="before")
    @classmethod
    def stable_provider(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
        if not normalized or len(normalized) > 80:
            raise ValueError("provider must be a stable lowercase identifier")
        return normalized

    @field_validator("cost_currency")
    @classmethod
    def currency_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized.isalpha():
            raise ValueError("cost currency must be an alphabetic code")
        return normalized

    @field_validator("options")
    @classmethod
    def safe_options(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_sensitive_metadata(value, "options")

    @model_validator(mode="after")
    def at_least_one_output(self):
        if not self.requested_outputs:
            raise ValueError("at least one requested output is required")
        return self


class ProcessingJobRetry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int | None = Field(default=None, ge=1)
    provider: str | None = Field(default=None, min_length=2, max_length=80)

    @field_validator("provider", mode="before")
    @classmethod
    def stable_provider(cls, value: str | None) -> str | None:
        return ProcessingJobCreate.stable_provider(value)


class ProcessingJobCancel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int | None = Field(default=None, ge=1)


class ProcessingOutputOut(BaseModel):
    output_type: str
    dataset_id: str
    quality_status: str


class ProcessingJobOut(BaseModel):
    id: str
    organization_id: str
    workspace_id: str | None
    asset_id: str | None
    acquisition_id: str | None
    fulfilment_job_id: str | None
    provider: str
    provider_job_reference: str | None
    source_dataset_ids: list[str]
    requested_outputs: list[str]
    generated_outputs: list[ProcessingOutputOut]
    status: str
    progress_percent: float
    stage: str | None
    processor_name: str | None
    processor_version: str | None
    estimated_cost_amount: int | None
    actual_cost_amount: int | None
    cost_currency: str
    error_code: str | None
    error_message: str | None
    quality_report: dict[str, Any]
    retry_count: int
    max_retries: int
    poll_count: int
    submission_generation: int
    next_poll_at: datetime | None
    submitted_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    cancelled_at: datetime | None
    lifecycle_version: int
    created_at: datetime
    updated_at: datetime


class ProcessingCycleOut(BaseModel):
    claimed: int
    submitted: int
    running: int
    completed: int
    needs_review: int
    failed: int
    retried: int
    cancelled: int


__all__ = [
    "ProcessingCycleOut",
    "ProcessingJobCancel",
    "ProcessingJobCreate",
    "ProcessingJobOut",
    "ProcessingJobRetry",
    "ProcessingOutputOut",
]
