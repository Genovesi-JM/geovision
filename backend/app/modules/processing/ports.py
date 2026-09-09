"""Provider ports owned by the processing domain."""

from typing import Any, Mapping, Protocol, runtime_checkable

from app.core.integration import IntegrationResult


@runtime_checkable
class ProcessingProvider(Protocol):
    provider_name: str

    def submit(
        self,
        request: Mapping[str, Any],
        *,
        idempotency_key: str,
    ) -> IntegrationResult[Mapping[str, Any]]: ...

    def get_status(self, external_reference: str) -> IntegrationResult[Mapping[str, Any]]: ...


__all__ = ["ProcessingProvider"]
