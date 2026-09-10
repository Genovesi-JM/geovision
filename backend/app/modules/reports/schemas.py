"""Strict API and narrative contracts for the report engine."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.reports.domain import normalize_report_type


class NarrativeSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    heading: str = Field(min_length=1, max_length=120)
    paragraphs: list[str] = Field(min_length=1, max_length=20)

    @field_validator("heading")
    @classmethod
    def clean_heading(cls, value: str) -> str:
        return value.strip()

    @field_validator("paragraphs")
    @classmethod
    def clean_paragraphs(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values]
        if any(not value or len(value) > 2_000 for value in cleaned):
            raise ValueError("narrative paragraphs must contain valid text")
        return cleaned


class NarrativeEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["geovision.report-narrative.v1"]
    executive_summary: str = Field(min_length=1, max_length=4_000)
    sections: list[NarrativeSection] = Field(min_length=1, max_length=20)
    evidence_ids: list[str] = Field(default_factory=list, max_length=1_000)
    limitations: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("executive_summary")
    @classmethod
    def clean_summary(cls, value: str) -> str:
        return value.strip()

    @field_validator("evidence_ids", "limitations")
    @classmethod
    def clean_strings(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values]
        if any(not value or len(value) > 1_000 for value in cleaned):
            raise ValueError("narrative references must contain valid text")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("narrative references must not contain duplicates")
        return cleaned


class ReportGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_type: str = Field(default="ASSET_INTELLIGENCE", min_length=2, max_length=80)
    title: str | None = Field(default=None, min_length=1, max_length=240)
    template_version: str = Field(default="1.0.0", min_length=1, max_length=40)
    acquisition_id: str | None = Field(default=None, min_length=1, max_length=36)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("report_type", mode="before")
    @classmethod
    def stable_report_type(cls, value: str) -> str:
        return normalize_report_type(value)

    @field_validator("title", "idempotency_key", "acquisition_id", mode="before")
    @classmethod
    def clean_optional(cls, value: Any) -> Any:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None


class ReportDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_lifecycle_version: int | None = Field(default=None, ge=1)
    note: str | None = Field(default=None, max_length=2_000)

    @field_validator("note", mode="before")
    @classmethod
    def clean_note(cls, value: Any) -> Any:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None


class ReportOut(BaseModel):
    id: str
    organization_id: str
    workspace_id: str | None
    asset_id: str
    acquisition_id: str | None
    report_type: str
    title: str
    template_version: str
    revision: int
    status: str
    qa_level: str
    context_schema_version: str
    context_sha256: str
    narrative_provider: str
    narrative_model: str | None
    narrative_model_version: str
    narrative_schema_version: str
    provenance: dict[str, Any]
    qa_result: dict[str, Any]
    output_dataset_id: str | None
    output_file_id: str | None
    supersedes_report_id: str | None
    generated_at: datetime | None
    approved_at: datetime | None
    published_at: datetime | None
    lifecycle_version: int
    created_at: datetime
    updated_at: datetime


class ReportDetailOut(ReportOut):
    context: dict[str, Any]
    narrative: dict[str, Any]


class ReportListOut(BaseModel):
    items: list[ReportOut]
    total: int


__all__ = [
    "NarrativeEnvelope",
    "NarrativeSection",
    "ReportDecisionRequest",
    "ReportDetailOut",
    "ReportGenerateRequest",
    "ReportListOut",
    "ReportOut",
]
