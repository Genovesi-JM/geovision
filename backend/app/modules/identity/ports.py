"""Identity-provider ports owned by the identity domain."""

from typing import Any, Mapping, Optional, Protocol, runtime_checkable

from app.core.integration import IntegrationResult
from app.modules.identity.domain import ExternalPrincipal, TokenUse


@runtime_checkable
class IdentityProvider(Protocol):
    provider_name: str

    def validate_token(
        self,
        token: str,
        *,
        token_use: TokenUse,
        expected_nonce: Optional[str] = None,
    ) -> IntegrationResult[ExternalPrincipal]: ...


@runtime_checkable
class InteractiveIdentityProvider(IdentityProvider, Protocol):
    """Optional browser authorization-code capabilities."""

    def authorization_url(self, request: Mapping[str, Any]) -> str: ...
    def exchange_code(
        self,
        request: Mapping[str, Any],
    ) -> IntegrationResult[Mapping[str, Any]]: ...


__all__ = ["IdentityProvider", "InteractiveIdentityProvider"]
