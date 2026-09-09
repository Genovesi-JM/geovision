"""Identity provider port owned by the identity domain."""

from typing import Any, Mapping, Protocol, runtime_checkable

from app.core.integration import IntegrationResult


@runtime_checkable
class IdentityProvider(Protocol):
    provider_name: str

    def authorization_url(self, request: Mapping[str, Any]) -> str: ...
    def exchange_code(
        self,
        request: Mapping[str, Any],
    ) -> IntegrationResult[Mapping[str, Any]]: ...


__all__ = ["IdentityProvider"]
