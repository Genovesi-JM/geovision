"""ERP provider port owned by GeoVision's order domain."""

from typing import Any, Mapping, Protocol, runtime_checkable

from app.core.integration import IntegrationResult


@runtime_checkable
class ERPProvider(Protocol):
    provider_name: str

    def upsert(
        self,
        document_type: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
    ) -> IntegrationResult[str]: ...

    def health(self) -> Mapping[str, Any]: ...


__all__ = ["ERPProvider"]
