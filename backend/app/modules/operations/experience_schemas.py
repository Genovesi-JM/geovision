"""Server-owned navigation and queue contracts for GeoVision Operations."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


InternalCapability = Literal[
    "dashboard",
    "organizations",
    "assets",
    "orders",
    "jobs",
    "missions",
    "processing",
    "reports_qa",
    "contractors",
    "inventory",
    "finance_sync",
    "integrations",
    "system_health",
]
ContractorCapability = Literal[
    "my_jobs",
    "job_status",
    "uploads",
    "profile",
    "documents",
]


class OperationsActorOut(BaseModel):
    user_id: str
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)


class OperationsNavigationItemOut(BaseModel):
    key: InternalCapability
    label: str
    path: str
    capability: InternalCapability


class OperationsExperienceOut(BaseModel):
    surface: Literal["INTERNAL_OPERATIONS"] = "INTERNAL_OPERATIONS"
    actor: OperationsActorOut
    capabilities: list[InternalCapability] = Field(default_factory=list)
    navigation: list[OperationsNavigationItemOut] = Field(default_factory=list)
    generated_at: datetime


class OperationsTotalsOut(BaseModel):
    organizations: int = Field(ge=0)
    assets: int = Field(ge=0)
    orders: int = Field(ge=0)
    jobs: int = Field(ge=0)
    missions: int = Field(ge=0)
    processing_jobs: int = Field(ge=0)
    reports_review: int = Field(ge=0)
    contractors: int = Field(ge=0)


class OperationsAttentionOut(BaseModel):
    failed_jobs: int = Field(ge=0)
    blocked_jobs: int = Field(ge=0)
    failed_processing: int = Field(ge=0)
    retry_wait_processing: int = Field(ge=0)
    needs_review_processing: int = Field(ge=0)
    reports_awaiting_review: int = Field(ge=0)
    dead_letter_integrations: int = Field(ge=0)


class OperationsSystemHealthOut(BaseModel):
    status: Literal["HEALTHY", "DEGRADED"]
    event_dead_letters: int = Field(ge=0)
    notification_dead_letters: int = Field(ge=0)
    integration_dead_letters: int = Field(ge=0)
    processing_failures: int = Field(ge=0)


class OperationsRecentItemOut(BaseModel):
    target_type: Literal["JOB", "PROCESSING", "REPORT"]
    target_id: str
    title: str
    status: str
    updated_at: datetime


class OperationsDashboardOut(BaseModel):
    generated_at: datetime
    totals: OperationsTotalsOut
    attention: OperationsAttentionOut
    health: OperationsSystemHealthOut | None = None
    recent: list[OperationsRecentItemOut] = Field(default_factory=list)


class OperationsJobQueueItemOut(BaseModel):
    id: str
    job_number: str
    title: str
    state: str
    priority: str
    scheduled_start: datetime | None = None
    assignee_type: Literal["CONTRACTOR", "STAFF", "UNASSIGNED"]
    updated_at: datetime


class OperationsProcessingQueueItemOut(BaseModel):
    id: str
    status: str
    stage: str | None = None
    retry_count: int = Field(ge=0)
    max_retries: int = Field(ge=0)
    retries_remaining: int = Field(ge=0)
    next_poll_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    updated_at: datetime


class OperationsReportQueueItemOut(BaseModel):
    id: str
    title: str
    status: str
    qa_level: str
    revision: int = Field(ge=1)
    lifecycle_version: int = Field(ge=1)
    asset_id: str
    updated_at: datetime


class OperationsIntegrationQueueItemOut(BaseModel):
    id: str
    provider: str
    resource_type: str
    status: str
    attempts: int = Field(ge=0)
    max_attempts: int = Field(ge=0)
    retries_remaining: int = Field(ge=0)
    next_attempt_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    updated_at: datetime


class OperationsQueuesOut(BaseModel):
    generated_at: datetime
    jobs: list[OperationsJobQueueItemOut] = Field(default_factory=list)
    processing: list[OperationsProcessingQueueItemOut] = Field(default_factory=list)
    reports_qa: list[OperationsReportQueueItemOut] = Field(default_factory=list)
    integrations: list[OperationsIntegrationQueueItemOut] = Field(default_factory=list)


class ContractorIdentityOut(BaseModel):
    id: str
    display_name: str
    resource_type: str
    status: str
    availability: str


class ContractorNavigationItemOut(BaseModel):
    key: ContractorCapability
    label: str
    path: str
    capability: ContractorCapability


class ContractorJobCountsOut(BaseModel):
    offered: int = Field(ge=0)
    scheduled: int = Field(ge=0)
    active: int = Field(ge=0)
    review: int = Field(ge=0)
    completed: int = Field(ge=0)


class ContractorExperienceOut(BaseModel):
    surface: Literal["CONTRACTOR"] = "CONTRACTOR"
    contractor: ContractorIdentityOut
    capabilities: list[ContractorCapability] = Field(default_factory=list)
    navigation: list[ContractorNavigationItemOut] = Field(default_factory=list)
    job_counts: ContractorJobCountsOut
    generated_at: datetime


__all__ = [
    "ContractorExperienceOut",
    "InternalCapability",
    "OperationsDashboardOut",
    "OperationsExperienceOut",
    "OperationsQueuesOut",
]
