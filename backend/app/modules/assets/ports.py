"""External-system ports owned by the assets domain."""

from typing import Any, Mapping, Protocol, runtime_checkable

from app.core.integration import IntegrationResult


@runtime_checkable
class GISProvider(Protocol):
    provider_name: str

    def query_layers(self, request: Mapping[str, Any]) -> IntegrationResult[Mapping[str, Any]]: ...


@runtime_checkable
class AssetManagementProvider(Protocol):
    provider_name: str

    def synchronize_asset(
        self,
        request: Mapping[str, Any],
    ) -> IntegrationResult[Mapping[str, Any]]: ...


__all__ = ["AssetManagementProvider", "GISProvider"]
