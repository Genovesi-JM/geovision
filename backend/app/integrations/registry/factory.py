"""Lazy managed-identity factories for registry policy adapters."""

from __future__ import annotations

from datetime import timedelta
from functools import lru_cache
from typing import Any, Mapping

from app.core.config import Settings, settings

from .feature_flags import (
    AzureAppConfigurationFeatureFlagEvaluator,
    FeatureFlagEvaluator,
    NullFeatureFlagEvaluator,
)
from .secrets import AzureKeyVaultSecretStore, NullSecretStore, SecretStore


def create_feature_flag_evaluator(
    config: Settings = settings,
    *,
    provider_loader: Any | None = None,
    credential_factory: Any | None = None,
) -> FeatureFlagEvaluator:
    """Build a lazy, read-only App Configuration evaluator or fail closed."""

    endpoint = config.azure_app_configuration_endpoint
    if not endpoint:
        return NullFeatureFlagEvaluator()
    provider: Any | None = None

    def snapshot_loader() -> Mapping[str, object]:
        nonlocal provider
        if provider is None:
            resolved_provider_loader = provider_loader
            resolved_credential_factory = credential_factory
            if resolved_provider_loader is None or resolved_credential_factory is None:
                try:
                    from azure.appconfiguration.provider import load
                    from azure.identity import DefaultAzureCredential
                except ImportError as exc:
                    raise RuntimeError(
                        "Azure App Configuration runtime is unavailable"
                    ) from exc
                resolved_provider_loader = resolved_provider_loader or load
                resolved_credential_factory = (
                    resolved_credential_factory or DefaultAzureCredential
                )
            credential_kwargs = {}
            if config.azure_managed_identity_client_id:
                credential_kwargs["managed_identity_client_id"] = (
                    config.azure_managed_identity_client_id
                )
            credential = resolved_credential_factory(**credential_kwargs)
            provider = resolved_provider_loader(
                endpoint=endpoint,
                credential=credential,
                feature_flag_enabled=True,
                feature_flag_refresh_enabled=True,
                refresh_interval=config.integration_feature_flag_refresh_seconds,
                startup_timeout=(
                    config.integration_feature_flag_startup_timeout_seconds
                ),
            )
        else:
            refresh = getattr(provider, "refresh", None)
            if callable(refresh):
                refresh()
        return dict(provider)

    return AzureAppConfigurationFeatureFlagEvaluator(
        snapshot_loader,
        refresh_interval=timedelta(
            seconds=config.integration_feature_flag_refresh_seconds
        ),
        max_staleness=timedelta(
            seconds=config.integration_feature_flag_max_staleness_seconds
        ),
    )


def create_secret_store(
    config: Settings = settings,
    *,
    client_factory: Any | None = None,
    credential_factory: Any | None = None,
) -> SecretStore:
    """Build a read-only Key Vault adapter for deployed managed identity."""

    if not config.is_deployed and client_factory is None:
        return NullSecretStore()
    cached_credential: Any | None = None

    def key_vault_client(vault_url: str):
        nonlocal cached_credential
        resolved_client_factory = client_factory
        resolved_credential_factory = credential_factory
        if resolved_client_factory is None or resolved_credential_factory is None:
            try:
                from azure.identity import DefaultAzureCredential
                from azure.keyvault.secrets import SecretClient
            except ImportError as exc:
                raise RuntimeError("Azure Key Vault runtime is unavailable") from exc
            resolved_client_factory = resolved_client_factory or SecretClient
            resolved_credential_factory = (
                resolved_credential_factory or DefaultAzureCredential
            )
        if cached_credential is None:
            credential_kwargs = {}
            if config.azure_managed_identity_client_id:
                credential_kwargs["managed_identity_client_id"] = (
                    config.azure_managed_identity_client_id
                )
            cached_credential = resolved_credential_factory(**credential_kwargs)
        return resolved_client_factory(
            vault_url=vault_url,
            credential=cached_credential,
        )

    return AzureKeyVaultSecretStore(key_vault_client)


@lru_cache(maxsize=1)
def get_feature_flag_evaluator() -> FeatureFlagEvaluator:
    return create_feature_flag_evaluator(settings)


@lru_cache(maxsize=1)
def get_secret_store() -> SecretStore:
    return create_secret_store(settings)


__all__ = [
    "create_feature_flag_evaluator",
    "create_secret_store",
    "get_feature_flag_evaluator",
    "get_secret_store",
]
