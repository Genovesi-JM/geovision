"""Explicit future-provider scaffolds with safe not-configured outcomes."""

from __future__ import annotations

from app.core.integration import (
    IntegrationFailure,
    IntegrationResult,
    IntegrationStatus,
)
from app.modules.processing.ports import (
    NormalizedProcessingOutput,
    ProcessingRequest,
    ProcessingStatus,
    ProcessingSubmission,
    ProviderArtifact,
)


class UnavailableProcessingProvider:
    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name

    def _result(self, operation: str):
        return IntegrationResult.failed(
            provider=self.provider_name,
            operation=operation,
            status=IntegrationStatus.NOT_CONFIGURED,
            failure=IntegrationFailure(
                code="not_configured",
                message=f"{self.provider_name} processing adapter is not configured",
            ),
        )

    def submit(
        self,
        request: ProcessingRequest,
        *,
        idempotency_key: str,
    ) -> IntegrationResult[ProcessingSubmission]:
        del request, idempotency_key
        return self._result("submit")

    def status(self, external_reference: str) -> IntegrationResult[ProcessingStatus]:
        del external_reference
        return self._result("status")

    def cancel(self, external_reference: str) -> IntegrationResult[bool]:
        del external_reference
        return self._result("cancel")

    def retrieve_outputs(
        self, external_reference: str
    ) -> IntegrationResult[tuple[ProviderArtifact, ...]]:
        del external_reference
        return self._result("retrieve_outputs")

    def normalize_outputs(
        self,
        outputs: tuple[ProviderArtifact, ...],
        *,
        requested_outputs: tuple[str, ...],
    ) -> IntegrationResult[tuple[NormalizedProcessingOutput, ...]]:
        del outputs, requested_outputs
        return self._result("normalize_outputs")


__all__ = ["UnavailableProcessingProvider"]
