"""Phase 28 construction and GIS adapter boundary contracts."""

from __future__ import annotations

import base64
import json
import uuid
from typing import Any, Callable

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.integration import IntegrationStatus
from app.integrations.construction import create_construction_provider
from app.integrations.construction.fake import FakeConstructionProvider
from app.integrations.construction.unavailable import UnavailableConstructionProvider
from app.integrations.gis import create_gis_provider
from app.integrations.gis.fake import FakeGISProvider
from app.integrations.gis.unavailable import UnavailableGISProvider
from app.modules.assets.ports import GISProvider
from app.modules.operations.ports import ConstructionProvider


TEST_FERNET_KEY = base64.urlsafe_b64encode(b"e" * 32).decode()
DEPLOYED_SETTINGS = {
    "_env_file": None,
    "env": "prod",
    "secret_key": "phase-28-production-signing-secret-value",
    "encryption_key": TEST_FERNET_KEY,
    "frontend_base": "https://geovision.example",
    "backend_base": "https://api.geovision.example",
}


def test_contract_fakes_keep_vendor_references_outside_geovision_ids() -> None:
    internal_id = uuid.uuid4()
    construction = FakeConstructionProvider()
    gis = FakeGISProvider()

    assert isinstance(construction, ConstructionProvider)
    assert isinstance(gis, GISProvider)

    construction_result = construction.synchronize_project(
        {
            "internal_id": internal_id,
            "provider_project_id": "must-not-become-the-geovision-id",
        },
        idempotency_key="project-sync-1",
    )
    repeated_construction_result = construction.synchronize_project(
        {"internal_id": internal_id},
        idempotency_key="project-sync-1",
    )
    gis_result = gis.query_layers(
        {
            "internal_id": internal_id,
            "provider_layer_id": "must-not-become-the-geovision-id",
        }
    )

    for result, resource_type in (
        (construction_result, "construction_project"),
        (gis_result, "gis_layer_collection"),
    ):
        assert result.status is IntegrationStatus.SIMULATED
        assert result.external_reference is not None
        assert result.external_reference.internal_id == internal_id
        assert result.external_reference.resource_type == resource_type
        assert result.external_reference.value != str(internal_id)
        assert "must-not-become-the-geovision-id" not in json.dumps(result.value)

    assert construction_result.value == {
        "synchronized": True,
        "source": "contract_fixture",
    }
    assert repeated_construction_result.external_reference == (
        construction_result.external_reference
    )
    assert gis_result.value["measurements_authoritative"] is False


def test_construction_fixture_requires_uuid_and_idempotency_key() -> None:
    provider = FakeConstructionProvider()

    missing_id = provider.synchronize_project({}, idempotency_key="sync-1")
    missing_key = provider.synchronize_project(
        {"internal_id": uuid.uuid4()},
        idempotency_key=" ",
    )
    invalid_key_type = provider.synchronize_project(
        {"internal_id": uuid.uuid4()},
        idempotency_key=None,  # type: ignore[arg-type]
    )

    assert missing_id.status is IntegrationStatus.FAILED
    assert missing_id.failure is not None
    assert missing_id.failure.code == "invalid_request"
    assert missing_key.status is IntegrationStatus.FAILED
    assert missing_key.failure is not None
    assert missing_key.failure.code == "invalid_request"
    assert invalid_key_type.status is IntegrationStatus.FAILED
    assert invalid_key_type.failure is not None
    assert invalid_key_type.failure.code == "invalid_request"
    with pytest.raises(TypeError):
        provider.synchronize_project({"internal_id": uuid.uuid4()})


def test_gis_fixture_rejects_missing_authoritative_internal_id() -> None:
    result = FakeGISProvider().query_layers({"provider_layer_id": "external-only"})

    assert result.status is IntegrationStatus.FAILED
    assert result.failure is not None
    assert result.failure.code == "invalid_request"


@pytest.mark.parametrize(
    ("provider_name", "expected_type"),
    (
        ("autodesk_aps", "AutodeskAPSConstructionScaffold"),
        ("procore", "ProcoreConstructionScaffold"),
        ("bentley_itwin", "BentleyITwinConstructionScaffold"),
        ("trimble", "TrimbleConstructionScaffold"),
    ),
)
def test_construction_vendor_scaffolds_are_explicitly_unavailable(
    provider_name: str,
    expected_type: str,
) -> None:
    config = Settings(
        _env_file=None,
        construction_provider=provider_name,
        integration_connect_timeout_seconds=2.5,
        integration_read_timeout_seconds=17.0,
    )

    provider = create_construction_provider(config)
    result = provider.synchronize_project(
        {"internal_id": uuid.uuid4(), "client_secret": "do-not-echo"},
        idempotency_key="phase-28",
    )

    assert type(provider).__name__ == expected_type
    assert isinstance(provider, ConstructionProvider)
    assert provider.timeout_policy.connect_seconds == 2.5
    assert provider.timeout_policy.read_seconds == 17.0
    assert result.status is IntegrationStatus.NOT_CONFIGURED
    assert result.failure is not None
    assert result.failure.code == "provider_not_configured"
    assert result.failure.retryable is False
    assert "do-not-echo" not in str(result)
    assert result.external_reference is None


@pytest.mark.parametrize(
    ("provider_name", "client_id_field", "client_secret_field"),
    (
        ("autodesk_aps", "autodesk_aps_client_id", "autodesk_aps_client_secret"),
        ("procore", "procore_client_id", "procore_client_secret"),
        ("bentley_itwin", "bentley_itwin_client_id", "bentley_itwin_client_secret"),
        ("trimble", "trimble_client_id", "trimble_client_secret"),
    ),
)
def test_credentials_do_not_turn_construction_scaffolds_into_live_adapters(
    provider_name: str,
    client_id_field: str,
    client_secret_field: str,
) -> None:
    sentinel = f"{provider_name}-credential-sentinel"
    config = Settings(
        _env_file=None,
        construction_provider=provider_name,
        **{
            client_id_field: sentinel,
            client_secret_field: sentinel,
        },
    )

    provider = create_construction_provider(config)
    result = provider.synchronize_project(
        {"internal_id": uuid.uuid4()},
        idempotency_key="phase-28",
    )

    assert provider.credentials_configured is True
    assert result.status is IntegrationStatus.NOT_CONFIGURED
    assert result.failure is not None
    assert result.failure.code == "adapter_unavailable"
    assert sentinel not in repr(vars(provider))
    assert sentinel not in str(result)


def test_arcgis_scaffold_stays_unavailable_with_or_without_credentials() -> None:
    missing = create_gis_provider(Settings(_env_file=None, gis_provider="arcgis"))
    configured = create_gis_provider(
        Settings(
            _env_file=None,
            gis_provider="arcgis",
            arcgis_client_id="arcgis-id-sentinel",
            arcgis_client_secret="arcgis-secret-sentinel",
        )
    )

    missing_result = missing.query_layers({"internal_id": uuid.uuid4()})
    configured_result = configured.query_layers({"internal_id": uuid.uuid4()})

    assert isinstance(missing, GISProvider)
    assert missing_result.status is IntegrationStatus.NOT_CONFIGURED
    assert missing_result.failure is not None
    assert missing_result.failure.code == "provider_not_configured"
    assert configured_result.status is IntegrationStatus.NOT_CONFIGURED
    assert configured_result.failure is not None
    assert configured_result.failure.code == "adapter_unavailable"
    assert "arcgis-secret-sentinel" not in repr(vars(configured))
    assert "arcgis-secret-sentinel" not in str(configured_result)


def test_enterprise_factories_disable_fakes_in_deployed_profiles() -> None:
    config = Settings(**DEPLOYED_SETTINGS)

    construction = create_construction_provider(config, provider_name="fake")
    gis = create_gis_provider(config, provider_name="fake")

    assert isinstance(construction, UnavailableConstructionProvider)
    assert isinstance(gis, UnavailableGISProvider)
    assert construction.synchronize_project(
        {"internal_id": uuid.uuid4()},
        idempotency_key="phase-28",
    ).failure.code == "fixture_disabled"
    assert gis.query_layers({"internal_id": uuid.uuid4()}).failure.code == (
        "fixture_disabled"
    )


@pytest.mark.parametrize(
    ("factory", "field_name", "method_name"),
    (
        (create_construction_provider, "construction_provider", "synchronize_project"),
        (create_gis_provider, "gis_provider", "query_layers"),
    ),
)
def test_enterprise_factories_fail_closed_for_disabled_and_unknown_selection(
    factory: Callable[..., Any],
    field_name: str,
    method_name: str,
) -> None:
    disabled = factory(Settings(_env_file=None, **{field_name: "none"}))
    unknown = factory(Settings(_env_file=None), provider_name="future_vendor")

    request = {"internal_id": uuid.uuid4()}
    if method_name == "synchronize_project":
        disabled_result = disabled.synchronize_project(
            request,
            idempotency_key="phase-28",
        )
        unknown_result = unknown.synchronize_project(
            request,
            idempotency_key="phase-28",
        )
    else:
        disabled_result = disabled.query_layers(request)
        unknown_result = unknown.query_layers(request)

    assert disabled_result.status is IntegrationStatus.NOT_CONFIGURED
    assert disabled_result.failure is not None
    assert disabled_result.failure.code == "integration_disabled"
    assert unknown_result.status is IntegrationStatus.NOT_CONFIGURED
    assert unknown_result.failure is not None
    assert unknown_result.failure.code == "unsupported_provider"


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    (
        ("construction_provider", "unknown", "CONSTRUCTION_PROVIDER"),
        ("gis_provider", "unknown", "GIS_PROVIDER"),
        ("construction_provider", "fake", "fake construction"),
        ("gis_provider", "fake", "fake GIS"),
    ),
)
def test_settings_reject_unknown_or_deployed_fake_enterprise_providers(
    field_name: str,
    value: str,
    message: str,
) -> None:
    values = dict(DEPLOYED_SETTINGS)
    values[field_name] = value
    with pytest.raises(ValidationError, match=message):
        Settings(**values)


def test_enterprise_credentials_are_redacted_and_status_is_boolean_only() -> None:
    sentinel = "phase-28-enterprise-credential-sentinel"
    credential_fields = {
        "autodesk_aps_client_id": sentinel,
        "autodesk_aps_client_secret": sentinel,
        "procore_client_id": sentinel,
        "procore_client_secret": sentinel,
        "bentley_itwin_client_id": sentinel,
        "bentley_itwin_client_secret": sentinel,
        "trimble_client_id": sentinel,
        "trimble_client_secret": sentinel,
        "arcgis_client_id": sentinel,
        "arcgis_client_secret": sentinel,
    }
    config = Settings(
        _env_file=None,
        construction_provider="autodesk_aps",
        gis_provider="arcgis",
        **credential_fields,
    )

    outputs = (
        repr(config),
        json.dumps(config.model_dump(), default=str),
        config.model_dump_json(),
        json.dumps(config.safe_summary()),
    )
    assert all(sentinel not in output for output in outputs)
    assert config.safe_summary()["providers"]["construction"] == "autodesk_aps"
    assert config.safe_summary()["providers"]["gis"] == "arcgis"
    for provider_name in (
        "autodesk_aps",
        "procore",
        "bentley_itwin",
        "trimble",
        "arcgis",
    ):
        assert config.safe_summary()["configured"][provider_name] is True


def test_partial_enterprise_credentials_are_not_reported_as_configured() -> None:
    config = Settings(
        _env_file=None,
        autodesk_aps_client_id="client-id-only",
        arcgis_client_secret="secret-only",
    )

    assert config.safe_summary()["configured"]["autodesk_aps"] is False
    assert config.safe_summary()["configured"]["arcgis"] is False
