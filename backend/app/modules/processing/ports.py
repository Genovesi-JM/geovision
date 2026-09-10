"""Typed provider port owned by the processing domain."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable

from app.core.integration import IntegrationResult


@dataclass(frozen=True, slots=True)
class ProcessingInput:
    filename: str
    content: bytes = field(repr=False)
    content_type: str = "application/octet-stream"
    sha256_hash: str | None = None


@dataclass(frozen=True, slots=True)
class ProcessingRequest:
    job_id: str
    name: str
    inputs: tuple[ProcessingInput, ...]
    requested_outputs: tuple[str, ...]
    options: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProcessingSubmission:
    external_reference: str
    state: str
    processor_name: str
    processor_version: str | None = None
    estimated_cost_amount: int | None = None


@dataclass(frozen=True, slots=True)
class ProcessingStatus:
    state: str
    progress_percent: float
    stage: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    actual_cost_amount: int | None = None


@dataclass(frozen=True, slots=True)
class ProviderArtifact:
    """Raw provider artifact before GeoVision output classification."""

    relative_path: str
    content: bytes = field(repr=False)
    content_type: str = "application/octet-stream"


@dataclass(frozen=True, slots=True)
class NormalizedProcessingOutput:
    dataset_type: str
    filename: str
    content: bytes = field(repr=False)
    content_type: str = "application/octet-stream"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class ProcessingProvider(Protocol):
    provider_name: str

    def submit(
        self,
        request: ProcessingRequest,
        *,
        idempotency_key: str,
    ) -> IntegrationResult[ProcessingSubmission]: ...

    def status(
        self, external_reference: str
    ) -> IntegrationResult[ProcessingStatus]: ...

    def cancel(self, external_reference: str) -> IntegrationResult[bool]: ...

    def retrieve_outputs(
        self, external_reference: str
    ) -> IntegrationResult[tuple[ProviderArtifact, ...]]: ...

    def normalize_outputs(
        self,
        outputs: tuple[ProviderArtifact, ...],
        *,
        requested_outputs: tuple[str, ...],
    ) -> IntegrationResult[tuple[NormalizedProcessingOutput, ...]]: ...


__all__ = [
    "NormalizedProcessingOutput",
    "ProcessingInput",
    "ProcessingProvider",
    "ProcessingRequest",
    "ProcessingStatus",
    "ProcessingSubmission",
    "ProviderArtifact",
]
