"""External construction-system port owned by operations."""

from typing import Any, Mapping, Protocol, runtime_checkable

from app.core.integration import IntegrationResult


@runtime_checkable
class ConstructionProvider(Protocol):
    provider_name: str

    def synchronize_project(
        self,
        request: Mapping[str, Any],
    ) -> IntegrationResult[Mapping[str, Any]]: ...


__all__ = ["ConstructionProvider"]
