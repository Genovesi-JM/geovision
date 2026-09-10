"""Phase 30 asset-management provider boundary contracts."""

from __future__ import annotations

import ast
import base64
from dataclasses import asdict
import json
from pathlib import Path
import uuid

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.integration import IntegrationStatus
from app.integrations.asset_management import create_asset_management_provider
from app.integrations.asset_management.fake import FakeAssetManagementProvider
from app.integrations.asset_management.unavailable import (
    UnavailableAssetManagementProvider,
)
from app.integrations.construction import create_construction_provider
from app.integrations.gis import create_gis_provider
from app.integrations.processing import create_processing_provider
from app.modules.assets.ports import (
    AssetManagementProvider,
    AssetSynchronizationReceipt,
    AssetSynchronizationRequest,
)


TEST_FERNET_KEY = base64.urlsafe_b64encode(b"m" * 32).decode()
DEPLOYED_SETTINGS = {
    "_env_file": None,
    "env": "prod",
    "secret_key": "phase-30-production-signing-secret-value",
    "encryption_key": TEST_FERNET_KEY,
    "frontend_base": "https://geovision.example",
    "backend_base": "https://api.geovision.example",
}


def test_asset_management_fake_accepts_typed_and_legacy_requests() -> None:
    internal_id = uuid.uuid4()
    provider = FakeAssetManagementProvider()
    typed_request = AssetSynchronizationRequest(
        internal_id=internal_id,
        asset_kind="quarry.site",
        external_reference="vendor-reference-must-stay-opaque",
        metadata={
            "volume": 999_999,
            "geology": "not-an-authoritative-claim",
            "safety": "not-a-provider-decision",
        },
    )

    typed = provider.synchronize_asset(
        typed_request,
        idempotency_key="phase-30-sync-1",
    )
    typed_repeat = provider.synchronize_asset(
        typed_request,
        idempotency_key="  phase-30-sync-1  ",
    )
    legacy = provider.synchronize_asset(
        {"internal_id": internal_id},
        idempotency_key="phase-30-legacy",
    )

    assert isinstance(provider, AssetManagementProvider)
    for result in (typed, typed_repeat, legacy):
        assert result.status is IntegrationStatus.SIMULATED
        assert isinstance(result.value, AssetSynchronizationReceipt)
        assert result.value.synchronized is True
        assert result.value.source == "contract_fixture"
        assert result.value.measurements_authoritative is False
        assert result.value.diagnostic_authority is False
        assert result.value.context_only is True
        assert result.external_reference is not None
        assert result.external_reference.internal_id == internal_id
        assert result.external_reference.resource_type == "asset_management_asset"
        assert result.external_reference.value != str(internal_id)

    assert typed_repeat.external_reference == typed.external_reference
    assert legacy.external_reference != typed.external_reference
    assert typed.external_reference is not None
    assert "vendor-reference-must-stay-opaque" not in typed.external_reference.value
    serialized_receipt = json.dumps(asdict(typed.value))
    assert all(
        unsupported not in serialized_receipt
        for unsupported in ("volume", "geology", "safety", "stability")
    )


def test_fake_reference_is_deterministic_for_asset_kind_and_idempotency() -> None:
    internal_id = uuid.uuid4()
    provider = FakeAssetManagementProvider()

    base = provider.synchronize_asset(
        {"internal_id": internal_id, "asset_kind": "mine"},
        idempotency_key="same-key",
    )
    normalized = provider.synchronize_asset(
        {"internal_id": str(internal_id), "asset_kind": " MINE "},
        idempotency_key="same-key",
    )
    different_kind = provider.synchronize_asset(
        {"internal_id": internal_id, "asset_kind": "quarry"},
        idempotency_key="same-key",
    )
    different_key = provider.synchronize_asset(
        {"internal_id": internal_id, "asset_kind": "mine"},
        idempotency_key="different-key",
    )

    assert base.external_reference == normalized.external_reference
    assert base.external_reference != different_kind.external_reference
    assert base.external_reference != different_key.external_reference


@pytest.mark.parametrize(
    ("query_input", "idempotency_key"),
    (
        ({}, "sync-1"),
        ({"internal_id": "not-a-uuid"}, "sync-1"),
        ({"internal_id": uuid.uuid4(), "asset_kind": "bad kind"}, "sync-1"),
        ({"internal_id": uuid.uuid4()}, ""),
        ({"internal_id": uuid.uuid4()}, " " * 3),
        ({"internal_id": uuid.uuid4()}, "x" * 201),
        ({"internal_id": uuid.uuid4()}, "contains\ncontrol"),
        ({"internal_id": uuid.uuid4()}, None),
    ),
)
def test_asset_management_fake_rejects_invalid_requests(
    query_input: object,
    idempotency_key: object,
) -> None:
    result = FakeAssetManagementProvider().synchronize_asset(
        query_input,  # type: ignore[arg-type]
        idempotency_key=idempotency_key,  # type: ignore[arg-type]
    )

    assert result.status is IntegrationStatus.FAILED
    assert result.failure is not None
    assert result.failure.code == "invalid_request"
    assert result.external_reference is None


def test_asset_management_write_requires_keyword_idempotency() -> None:
    provider = FakeAssetManagementProvider()
    request = {"internal_id": uuid.uuid4()}

    with pytest.raises(TypeError):
        provider.synchronize_asset(request)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        provider.synchronize_asset(request, "positional-key")  # type: ignore[misc]


def test_seequent_scaffold_distinguishes_configuration_from_availability() -> None:
    missing = create_asset_management_provider(
        Settings(
            _env_file=None,
            asset_management_provider="seequent",
            integration_connect_timeout_seconds=2.5,
            integration_read_timeout_seconds=17,
        )
    )
    configured = create_asset_management_provider(
        Settings(
            _env_file=None,
            asset_management_provider="seequent",
            seequent_client_id="seequent-client-id-sentinel",
            seequent_client_secret="seequent-client-secret-sentinel",
        )
    )

    missing_result = missing.synchronize_asset(
        {"internal_id": uuid.uuid4()},
        idempotency_key="phase-30",
    )
    configured_result = configured.synchronize_asset(
        {
            "internal_id": uuid.uuid4(),
            "client_secret": "request-secret-must-not-echo",
        },
        idempotency_key="phase-30",
    )

    assert isinstance(missing, AssetManagementProvider)
    assert type(missing).__name__ == "SeequentAssetManagementScaffold"
    assert missing.credentials_configured is False
    assert missing.timeout_policy.connect_seconds == 2.5
    assert missing.timeout_policy.read_seconds == 17
    assert missing.timeout_policy.write_seconds == 17
    assert missing_result.status is IntegrationStatus.NOT_CONFIGURED
    assert missing_result.failure is not None
    assert missing_result.failure.code == "provider_not_configured"
    assert missing_result.failure.retryable is False

    assert configured.credentials_configured is True
    assert configured_result.status is IntegrationStatus.NOT_CONFIGURED
    assert configured_result.failure is not None
    assert configured_result.failure.code == "adapter_unavailable"
    assert "seequent-client-id-sentinel" not in repr(vars(configured))
    assert "seequent-client-secret-sentinel" not in repr(vars(configured))
    assert "request-secret-must-not-echo" not in str(configured_result)


def test_mine_enterprise_scaffold_requires_phase_32_selection_and_sandbox() -> None:
    provider = create_asset_management_provider(
        Settings(_env_file=None, asset_management_provider="mine_enterprise")
    )
    result = provider.synchronize_asset(
        AssetSynchronizationRequest(
            internal_id=uuid.uuid4(),
            asset_kind="mine",
        ),
        idempotency_key="phase-30",
    )

    assert isinstance(provider, AssetManagementProvider)
    assert type(provider).__name__ == "MineEnterpriseSystemScaffold"
    assert provider.credentials_configured is False
    assert result.status is IntegrationStatus.NOT_CONFIGURED
    assert result.failure is not None
    assert result.failure.code == "provider_not_configured"
    assert "sandbox" in result.failure.message
    assert result.external_reference is None


def test_asset_management_factory_disables_fakes_in_deployed_profiles() -> None:
    config = Settings(**DEPLOYED_SETTINGS)

    for override in ("fake", "deterministic"):
        provider = create_asset_management_provider(config, provider_name=override)
        result = provider.synchronize_asset(
            {"internal_id": uuid.uuid4()},
            idempotency_key="phase-30",
        )

        assert isinstance(provider, UnavailableAssetManagementProvider)
        assert result.status is IntegrationStatus.NOT_CONFIGURED
        assert result.failure is not None
        assert result.failure.code == "fixture_disabled"


@pytest.mark.parametrize("selector", ("fake", "deterministic"))
def test_asset_management_factory_exposes_fakes_only_locally(selector: str) -> None:
    provider = create_asset_management_provider(
        Settings(_env_file=None, asset_management_provider=selector)
    )

    assert isinstance(provider, FakeAssetManagementProvider)


@pytest.mark.parametrize("selector", ("none", "null"))
def test_asset_management_factory_disabled_selectors_fail_closed(
    selector: str,
) -> None:
    provider = create_asset_management_provider(
        Settings(_env_file=None, asset_management_provider=selector)
    )
    result = provider.synchronize_asset(
        {"internal_id": uuid.uuid4()},
        idempotency_key="phase-30",
    )

    assert result.status is IntegrationStatus.NOT_CONFIGURED
    assert result.failure is not None
    assert result.failure.code == "integration_disabled"


def test_asset_management_factory_unknown_override_fails_closed() -> None:
    provider = create_asset_management_provider(
        Settings(_env_file=None),
        provider_name="future_vendor",
    )
    result = provider.synchronize_asset(
        {"internal_id": uuid.uuid4()},
        idempotency_key="phase-30",
    )

    assert result.status is IntegrationStatus.NOT_CONFIGURED
    assert result.failure is not None
    assert result.failure.code == "unsupported_provider"


@pytest.mark.parametrize(
    ("value", "message"),
    (
        ("unknown", "ASSET_MANAGEMENT_PROVIDER"),
        ("fake", "fake asset-management"),
        ("deterministic", "fake asset-management"),
    ),
)
def test_settings_reject_unknown_or_deployed_fake_asset_management_provider(
    value: str,
    message: str,
) -> None:
    values = dict(DEPLOYED_SETTINGS)
    values["asset_management_provider"] = value

    with pytest.raises(ValidationError, match=message):
        Settings(**values)


def test_seequent_credentials_are_redacted_and_summary_is_boolean_only() -> None:
    sentinel = "phase-30-seequent-credential-sentinel"
    config = Settings(
        _env_file=None,
        asset_management_provider="seequent",
        seequent_client_id=sentinel,
        seequent_client_secret=sentinel,
    )

    outputs = (
        repr(config),
        json.dumps(config.model_dump(), default=str),
        config.model_dump_json(),
        json.dumps(config.safe_summary()),
    )
    assert all(sentinel not in output for output in outputs)
    assert config.safe_summary()["providers"]["asset_management"] == "seequent"
    assert config.safe_summary()["configured"]["seequent"] is True

    partial = Settings(_env_file=None, seequent_client_id="client-id-only")
    assert partial.safe_summary()["configured"]["seequent"] is False


def test_asset_management_package_has_no_network_or_vendor_sdk_imports() -> None:
    package = Path(__file__).parents[1] / "app" / "integrations" / "asset_management"
    forbidden_roots = {
        "arcgis",
        "bentley",
        "httpx",
        "requests",
        "seequent",
        "socket",
    }

    imports: set[str] = set()
    for source_path in package.glob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imports.add(node.module.split(".", 1)[0])

    assert imports.isdisjoint(forbidden_roots)


def test_existing_bentley_arcgis_and_miteco_capabilities_are_reused() -> None:
    bentley_construction = create_construction_provider(
        Settings(_env_file=None, construction_provider="bentley_itwin")
    )
    bentley_processing = create_processing_provider(
        Settings(_env_file=None, processing_provider="bentley_reality_modeling")
    )
    arcgis = create_gis_provider(Settings(_env_file=None, gis_provider="arcgis"))
    miteco = create_gis_provider(Settings(_env_file=None, gis_provider="miteco"))

    try:
        assert type(bentley_construction).__name__ == (
            "BentleyITwinConstructionScaffold"
        )
        assert type(bentley_processing).__name__ == "UnavailableProcessingProvider"
        assert type(arcgis).__name__ == "ArcGISProviderScaffold"
        assert type(miteco).__name__ == "MitecoOgcFeaturesProvider"
        for duplicate_name in (
            "bentley_itwin",
            "bentley_reality_modeling",
            "arcgis",
            "miteco",
        ):
            duplicate = create_asset_management_provider(
                Settings(_env_file=None),
                provider_name=duplicate_name,
            )
            result = duplicate.synchronize_asset(
                {"internal_id": uuid.uuid4()},
                idempotency_key="phase-30",
            )
            assert result.failure is not None
            assert result.failure.code == "unsupported_provider"
    finally:
        miteco.client.close()
