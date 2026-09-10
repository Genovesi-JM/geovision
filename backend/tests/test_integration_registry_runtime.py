"""Runtime wiring tests for App Configuration and Key Vault adapters."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.integrations.registry import (
    FeatureFlagTarget,
    NullFeatureFlagEvaluator,
    NullSecretStore,
)
from app.integrations.registry.factory import (
    create_feature_flag_evaluator,
    create_secret_store,
)


FLAG = "geovision.integrations.construction.fake"


class _Provider(dict):
    def __init__(self) -> None:
        super().__init__(
            {
                "ENV": "staging",
                "OBJECT_STORAGE_PROVIDER": "azure_blob",
                "SERVICE_BUS_TOPIC": "geovision-events",
                "feature_management": {
                    "feature_flags": {
                        FLAG: {
                            "id": FLAG,
                            "enabled": True,
                            "conditions": {},
                        }
                    }
                },
            }
        )
        self.refresh_calls = 0

    def refresh(self) -> None:
        self.refresh_calls += 1


def test_feature_flag_factory_is_lazy_and_uses_managed_identity_contract() -> None:
    provider = _Provider()
    loader_calls: list[dict[str, object]] = []
    credential_calls: list[dict[str, object]] = []

    def credential_factory(**kwargs):
        credential_calls.append(kwargs)
        return "managed-identity-credential"

    def provider_loader(**kwargs):
        loader_calls.append(kwargs)
        return provider

    config = Settings(
        _env_file=None,
        azure_app_configuration_endpoint="https://geovision-flags.azconfig.io/",
        azure_managed_identity_client_id="9a5b7fea-26a1-4b49-8c3b-43c627298ef2",
        integration_feature_flag_refresh_seconds=60,
        integration_feature_flag_max_staleness_seconds=600,
        integration_feature_flag_startup_timeout_seconds=4,
    )
    evaluator = create_feature_flag_evaluator(
        config,
        provider_loader=provider_loader,
        credential_factory=credential_factory,
    )

    assert loader_calls == []
    assert evaluator.allows_rollout(
        FLAG,
        target=FeatureFlagTarget(
            organization_id=UUID("74d739f3-dd4e-45ec-9f61-42629ebb5206"),
            workspace_id=UUID("a7912c43-244a-4282-89db-dfdd12b1fd37"),
        ),
        authorized=True,
        entitled=True,
    )
    assert credential_calls == [
        {"managed_identity_client_id": "9a5b7fea-26a1-4b49-8c3b-43c627298ef2"}
    ]
    assert loader_calls == [
        {
            "endpoint": "https://geovision-flags.azconfig.io",
            "credential": "managed-identity-credential",
            "feature_flag_enabled": True,
            "feature_flag_refresh_enabled": True,
            "refresh_interval": 60,
            "startup_timeout": 4,
        }
    ]
    assert provider.refresh_calls == 0


def test_feature_flag_evaluator_ignores_unrelated_raw_configuration_values() -> None:
    provider = {
        "ENV": "staging",
        "OBJECT_STORAGE_PROVIDER": "azure_blob",
        ".appconfig.featureflag/geovision.integrations.construction.fake": {
            "id": FLAG,
            "enabled": True,
            "conditions": {},
        },
    }
    config = Settings(
        _env_file=None,
        azure_app_configuration_endpoint="https://geovision-flags.azconfig.io",
    )
    evaluator = create_feature_flag_evaluator(
        config,
        provider_loader=lambda **_kwargs: provider,
        credential_factory=lambda **_kwargs: "managed-identity-credential",
    )

    assert evaluator.allows_rollout(
        FLAG,
        target=FeatureFlagTarget(
            organization_id=UUID("74d739f3-dd4e-45ec-9f61-42629ebb5206"),
            workspace_id=UUID("a7912c43-244a-4282-89db-dfdd12b1fd37"),
        ),
        authorized=True,
        entitled=True,
    )


def test_feature_flag_factory_and_secret_store_fail_closed_when_unconfigured() -> None:
    config = Settings(_env_file=None)

    assert isinstance(create_feature_flag_evaluator(config), NullFeatureFlagEvaluator)
    assert isinstance(create_secret_store(config), NullSecretStore)


def test_secret_store_factory_uses_validated_vault_and_redacts_values() -> None:
    client_calls: list[dict[str, object]] = []
    credential_calls: list[dict[str, object]] = []
    secret_calls: list[tuple[str, str | None]] = []

    class Client:
        def get_secret(self, name: str, version: str | None = None):
            secret_calls.append((name, version))
            return SimpleNamespace(value="resolved-but-redacted")

    def credential_factory(**kwargs):
        credential_calls.append(kwargs)
        return "managed-identity-credential"

    def client_factory(**kwargs):
        client_calls.append(kwargs)
        return Client()

    store = create_secret_store(
        Settings(
            _env_file=None,
            azure_managed_identity_client_id="9a5b7fea-26a1-4b49-8c3b-43c627298ef2",
        ),
        client_factory=client_factory,
        credential_factory=credential_factory,
    )
    secret = store.resolve(
        "https://geovisionvault.vault.azure.net/secrets/provider-token/version-1"
    )

    assert secret.reveal() == "resolved-but-redacted"
    assert "resolved-but-redacted" not in repr(secret)
    assert credential_calls == [
        {"managed_identity_client_id": "9a5b7fea-26a1-4b49-8c3b-43c627298ef2"}
    ]
    assert client_calls == [
        {
            "vault_url": "https://geovisionvault.vault.azure.net",
            "credential": "managed-identity-credential",
        }
    ]
    assert secret_calls == [("provider-token", "version-1")]


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://geovision.azconfig.io",
        "https://geovision.azconfig.io/path",
        "https://geovision.azconfig.io:443",
        "https://user@geovision.azconfig.io",
        "https://not-app-configuration.example.test",
    ],
)
def test_app_configuration_endpoint_rejects_noncanonical_origins(endpoint: str) -> None:
    with pytest.raises(ValidationError, match="canonical Azure HTTPS origin"):
        Settings(_env_file=None, azure_app_configuration_endpoint=endpoint)


def test_feature_flag_refresh_window_is_validated_and_summary_is_secret_free() -> None:
    with pytest.raises(ValidationError, match="MAX_STALENESS_SECONDS"):
        Settings(
            _env_file=None,
            integration_feature_flag_refresh_seconds=300,
            integration_feature_flag_max_staleness_seconds=299,
        )

    endpoint = "https://geovision-flags.azconfig.io"
    summary = Settings(
        _env_file=None,
        azure_app_configuration_endpoint=endpoint,
    ).safe_summary()
    assert summary["configured"]["azure_app_configuration"] is True
    assert endpoint not in str(summary)
