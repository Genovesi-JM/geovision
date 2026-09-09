"""Identity-provider composition from typed application settings."""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from app.core.config import Settings, settings
from app.core.integration import IntegrationConfigurationError, IntegrationResult
from app.modules.identity.domain import ExternalPrincipal, TokenUse
from app.modules.identity.ports import IdentityProvider

from .entra_external_id import (
    EntraExternalIdProvider,
    JsonDocumentFetcher,
)
from .internal import InternalIdentityProvider


class TransitionIdentityProvider:
    """Explicitly route known token purposes during the provider cutover."""

    provider_name = "transition"

    def __init__(
        self,
        *,
        internal: InternalIdentityProvider,
        entra_external_id: EntraExternalIdProvider,
    ) -> None:
        self._internal = internal
        self._entra_external_id = entra_external_id

    def validate_token(
        self,
        token: str,
        *,
        token_use: TokenUse,
        expected_nonce: Optional[str] = None,
    ) -> IntegrationResult[ExternalPrincipal]:
        # Purpose comes from the trusted route/dependency, never an unverified
        # token header or claim. This keeps HS256 and RS256 validation separate.
        if token_use is TokenUse.INTERNAL_SESSION:
            return self._internal.validate_token(
                token,
                token_use=token_use,
                expected_nonce=expected_nonce,
            )
        if token_use is TokenUse.API_ACCESS_TOKEN:
            return self._entra_external_id.validate_token(
                token,
                token_use=token_use,
                expected_nonce=expected_nonce,
            )
        return self._entra_external_id.validate_token(
            token,
            token_use=token_use,
            expected_nonce=expected_nonce,
        )


def create_entra_external_id_provider(
    config: Settings = settings,
    *,
    fetcher: Optional[JsonDocumentFetcher] = None,
) -> EntraExternalIdProvider:
    discovery_url = getattr(
        config,
        "effective_entra_external_id_discovery_url",
        None,
    )
    if not discovery_url:
        discovery_url = config.entra_external_id_discovery_url
    if not discovery_url and config.entra_external_id_issuer:
        discovery_url = (
            config.entra_external_id_issuer.rstrip("/")
            + "/.well-known/openid-configuration"
        )
    return EntraExternalIdProvider(
        issuer=config.entra_external_id_issuer,
        audience=config.entra_external_id_audience,
        tenant_id=config.entra_external_id_tenant_id,
        discovery_url=discovery_url,
        required_scope=config.entra_external_id_required_scope,
        authorized_party=config.entra_external_id_authorized_party,
        clock_skew_seconds=config.entra_external_id_clock_skew_seconds,
        jwks_cache_seconds=config.entra_external_id_jwks_cache_seconds,
        connect_timeout_seconds=config.integration_connect_timeout_seconds,
        read_timeout_seconds=config.integration_read_timeout_seconds,
        fetcher=fetcher,
    )


def create_identity_provider(
    config: Settings = settings,
    *,
    fetcher: Optional[JsonDocumentFetcher] = None,
) -> IdentityProvider:
    provider_name = config.identity_provider
    internal = InternalIdentityProvider(issuer=config.internal_token_issuer)
    if provider_name == "internal":
        return internal

    if provider_name in {"entra_external_id", "transition"}:
        entra = create_entra_external_id_provider(config, fetcher=fetcher)
        if provider_name == "entra_external_id":
            return entra
        return TransitionIdentityProvider(
            internal=internal,
            entra_external_id=entra,
        )

    raise IntegrationConfigurationError(
        provider=provider_name or "identity",
        operation="initialize",
        message="unsupported identity provider",
    )


@lru_cache(maxsize=1)
def get_identity_provider() -> IdentityProvider:
    """Return one process-local provider so discovery/JWKS caches are reused."""

    return create_identity_provider(settings)


def clear_identity_provider_cache() -> None:
    get_identity_provider.cache_clear()


__all__ = [
    "TransitionIdentityProvider",
    "clear_identity_provider_cache",
    "create_entra_external_id_provider",
    "create_identity_provider",
    "get_identity_provider",
]
