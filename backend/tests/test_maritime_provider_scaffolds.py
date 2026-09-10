"""Phase 31 maritime provider contracts and fail-closed scaffolds."""

from __future__ import annotations

import ast
import base64
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.integration import IntegrationStatus
from app.integrations.maritime import create_maritime_provider
from app.integrations.maritime.fake import DeterministicMaritimeProvider
from app.integrations.maritime.scaffolds import (
    PUERTOS_OCEANOGRAPHY_TERMS_URL,
)
from app.integrations.maritime.unavailable import UnavailableMaritimeProvider
from app.modules.monitoring.ports import (
    MaritimeContextRequest,
    MaritimeContextResult,
    MaritimeProvider,
    MaritimeSourceKind,
)


TEST_FERNET_KEY = base64.urlsafe_b64encode(b"p" * 32).decode()
DEPLOYED_SETTINGS = {
    "_env_file": None,
    "env": "prod",
    "secret_key": "phase-31-production-signing-secret-value",
    "encryption_key": TEST_FERNET_KEY,
    "frontend_base": "https://geovision.example",
    "backend_base": "https://api.geovision.example",
}


def _request(internal_id: uuid.UUID | None = None) -> MaritimeContextRequest:
    return MaritimeContextRequest(
        internal_id=internal_id or uuid.uuid4(),
        latitude=38.7223,
        longitude=-9.1393,
        starts_at=datetime(2025, 1, 2, 9, 0, tzinfo=timezone.utc),
        ends_at=datetime(2025, 1, 2, 12, 0, tzinfo=timezone.utc),
        max_distance_km=25.0,
        limit=2,
    )


def test_maritime_fake_accepts_typed_and_mapping_requests_deterministically() -> None:
    internal_id = uuid.uuid4()
    provider = create_maritime_provider(
        Settings(_env_file=None, maritime_provider="fake")
    )
    typed = provider.operational_context(_request(internal_id))
    mapped = provider.operational_context(
        {
            "internal_id": str(internal_id),
            "latitude": 38.7223,
            "longitude": -9.1393,
            "starts_at": "2025-01-02T09:00:00Z",
            "ends_at": "2025-01-02T12:00:00+00:00",
            "max_distance_km": 25,
            "limit": 2,
            "api_key": "mapping-secret-must-not-be-retained",
            "provider_reference": "caller-reference-must-stay-opaque",
        }
    )

    assert isinstance(provider, MaritimeProvider)
    assert isinstance(provider, DeterministicMaritimeProvider)
    for result in (typed, mapped):
        assert result.status is IntegrationStatus.SIMULATED
        assert isinstance(result.value, MaritimeContextResult)
        assert result.value.internal_id == internal_id
        assert result.value.measurements_authoritative is False
        assert result.value.context_only is True
        assert result.value.navigation_authority is False
        assert result.value.diagnostic_authority is False
        assert len(result.value.readings) == 2
        assert result.external_reference is not None
        assert result.external_reference.internal_id == internal_id
        assert result.external_reference.resource_type == "maritime_context"
        assert result.external_reference.value != str(internal_id)

    assert typed.external_reference == mapped.external_reference
    assert typed.value == mapped.value
    assert typed.value is not None
    assert {reading.source_kind for reading in typed.value.readings} == {
        MaritimeSourceKind.OBSERVED,
        MaritimeSourceKind.MODEL,
    }
    assert {reading.metric for reading in typed.value.readings} == {
        "significant_wave_height",
        "water_temperature",
    }
    assert {reading.unit for reading in typed.value.readings} == {"degC", "m"}
    for reading in typed.value.readings:
        assert reading.valid_at == datetime(2025, 1, 2, 12, 0, tzinfo=timezone.utc)
        assert reading.station_reference
        assert reading.latitude == 38.7223
        assert reading.longitude == -9.1393
        assert reading.provider_reference
        assert reading.quality == "simulated"
        assert reading.source == "geovision_contract_fixture"
        assert reading.license_id == "GEOVISION-CONTRACT-FIXTURE"
        assert reading.attribution
        assert reading.provenance["fixture"] is True
        assert reading.provenance["source_kind"] == reading.source_kind.value

    serialized = json.dumps(asdict(typed.value), default=str)
    assert "mapping-secret-must-not-be-retained" not in serialized
    assert "caller-reference-must-stay-opaque" not in serialized


def test_maritime_fake_honors_result_bound_and_normalizes_naive_time_to_utc() -> None:
    result = DeterministicMaritimeProvider().operational_context(
        {
            "internal_id": uuid.uuid4(),
            "latitude": -90,
            "longitude": 180,
            "ends_at": datetime(2025, 4, 3, 2, 1),
            "limit": 1,
        }
    )

    assert result.status is IntegrationStatus.SIMULATED
    assert isinstance(result.value, MaritimeContextResult)
    assert len(result.value.readings) == 1
    reading = result.value.readings[0]
    assert reading.latitude == -90
    assert reading.longitude == 180
    assert reading.valid_at == datetime(2025, 4, 3, 2, 1, tzinfo=timezone.utc)

    with pytest.raises(TypeError):
        MaritimeContextResult(  # type: ignore[call-arg]
            internal_id=uuid.uuid4(),
            readings=(),
            context_only=False,
        )


@pytest.mark.parametrize(
    "query_input",
    (
        {},
        {"internal_id": "not-a-uuid", "latitude": 0, "longitude": 0},
        {"internal_id": uuid.uuid4(), "latitude": True, "longitude": 0},
        {"internal_id": uuid.uuid4(), "latitude": 90.1, "longitude": 0},
        {"internal_id": uuid.uuid4(), "latitude": 0, "longitude": -180.1},
        {
            "internal_id": uuid.uuid4(),
            "latitude": 0,
            "longitude": 0,
            "starts_at": "not-a-time",
        },
        {
            "internal_id": uuid.uuid4(),
            "latitude": 0,
            "longitude": 0,
            "starts_at": "2025-01-02T00:00:00Z",
            "ends_at": "2025-01-01T00:00:00Z",
        },
        {
            "internal_id": uuid.uuid4(),
            "latitude": 0,
            "longitude": 0,
            "max_distance_km": 0,
        },
        {
            "internal_id": uuid.uuid4(),
            "latitude": 0,
            "longitude": 0,
            "limit": 501,
        },
        {
            "internal_id": uuid.uuid4(),
            "latitude": 0,
            "longitude": 0,
            "limit": 1.5,
        },
        MaritimeContextRequest(
            internal_id=uuid.uuid4(),
            latitude=float("nan"),
            longitude=0,
        ),
    ),
)
def test_maritime_fake_revalidates_typed_and_mapping_query_bounds(
    query_input: object,
) -> None:
    result = DeterministicMaritimeProvider().operational_context(
        query_input  # type: ignore[arg-type]
    )

    assert result.status is IntegrationStatus.FAILED
    assert result.failure is not None
    assert result.failure.code == "invalid_request"
    assert result.external_reference is None


@pytest.mark.parametrize("selector", ("none", "null"))
def test_disabled_maritime_selectors_fail_closed(selector: str) -> None:
    provider = create_maritime_provider(
        Settings(_env_file=None, maritime_provider=selector)
    )
    result = provider.operational_context(_request())

    assert isinstance(provider, MaritimeProvider)
    assert isinstance(provider, UnavailableMaritimeProvider)
    assert result.status is IntegrationStatus.NOT_CONFIGURED
    assert result.failure is not None
    assert result.failure.code == "integration_disabled"


@pytest.mark.parametrize(
    ("selector", "class_name", "failure_code"),
    (
        (
            "marinetraffic",
            "MarineTrafficMaritimeScaffold",
            "provider_not_configured",
        ),
        ("kpler", "KplerMaritimeScaffold", "provider_not_configured"),
        (
            "puertos_del_estado",
            "PuertosDelEstadoMaritimeScaffold",
            "authorization_terms_not_approved",
        ),
    ),
)
def test_named_maritime_providers_are_explicit_unavailable_scaffolds(
    selector: str,
    class_name: str,
    failure_code: str,
) -> None:
    provider = create_maritime_provider(
        Settings(
            _env_file=None,
            maritime_provider=selector,
            integration_connect_timeout_seconds=2.5,
            integration_read_timeout_seconds=17,
        )
    )
    result = provider.operational_context(
        {
            "internal_id": uuid.uuid4(),
            "latitude": 38,
            "longitude": -9,
            "authorization": "Bearer maritime-secret-must-not-echo",
        }
    )

    assert isinstance(provider, MaritimeProvider)
    assert type(provider).__name__ == class_name
    assert provider.timeout_policy.connect_seconds == 2.5
    assert provider.timeout_policy.read_seconds == 17
    assert provider.timeout_policy.write_seconds == 17
    assert result.status is IntegrationStatus.NOT_CONFIGURED
    assert result.failure is not None
    assert result.failure.code == failure_code
    assert result.failure.retryable is False
    assert result.value is None
    assert result.external_reference is None
    assert "maritime-secret-must-not-echo" not in str(result)


def test_puertos_scaffold_requires_specific_redistribution_authorization() -> None:
    provider = create_maritime_provider(
        Settings(_env_file=None, maritime_provider="puertos-del-estado")
    )
    result = provider.operational_context(_request())

    assert provider.provider_name == "puertos_del_estado"
    assert provider.terms_url == PUERTOS_OCEANOGRAPHY_TERMS_URL
    assert result.failure is not None
    assert result.failure.code == "authorization_terms_not_approved"
    assert "third-party SaaS display" in result.failure.message
    assert "written permission" in result.failure.message


def test_ais_scaffolds_never_claim_navigation_or_safety_authority() -> None:
    for selector in ("marinetraffic", "kpler"):
        result = create_maritime_provider(
            Settings(_env_file=None, maritime_provider=selector)
        ).operational_context(_request())

        assert result.failure is not None
        assert "collision-avoidance or safety authority" in result.failure.message


def test_maritime_factory_disables_fakes_in_deployed_profiles() -> None:
    config = Settings(**DEPLOYED_SETTINGS)

    for override in ("fake", "deterministic"):
        provider = create_maritime_provider(config, provider_name=override)
        result = provider.operational_context(_request())

        assert isinstance(provider, UnavailableMaritimeProvider)
        assert result.status is IntegrationStatus.NOT_CONFIGURED
        assert result.failure is not None
        assert result.failure.code == "fixture_disabled"


@pytest.mark.parametrize("selector", ("fake", "deterministic"))
def test_settings_rejects_deployed_maritime_fixtures(selector: str) -> None:
    values = dict(DEPLOYED_SETTINGS)
    values["maritime_provider"] = selector

    with pytest.raises(ValidationError, match="fake maritime provider"):
        Settings(**values)


def test_unknown_maritime_selection_fails_closed() -> None:
    with pytest.raises(ValidationError, match="MARITIME_PROVIDER"):
        Settings(_env_file=None, maritime_provider="unknown")

    provider = create_maritime_provider(
        Settings(_env_file=None), provider_name="future_vendor"
    )
    result = provider.operational_context(_request())
    assert result.failure is not None
    assert result.failure.code == "unsupported_provider"


@pytest.mark.parametrize(
    "selector",
    ("marinetraffic", "kpler", "puertos_del_estado"),
)
def test_maritime_configuration_summary_never_implies_live_access(
    selector: str,
) -> None:
    config = Settings(_env_file=None, maritime_provider=selector)
    summary = config.safe_summary()

    assert summary["providers"]["maritime"] == selector
    assert summary["configured"]["maritime"] is False
    assert not hasattr(config, "marinetraffic_api_key")
    assert not hasattr(config, "kpler_api_key")
    assert not hasattr(config, "puertos_del_estado_api_key")


def test_maritime_package_has_no_network_vendor_or_existing_provider_imports() -> None:
    package = Path(__file__).parents[1] / "app" / "integrations" / "maritime"
    forbidden_roots = {
        "httpx",
        "kpler",
        "marinetraffic",
        "requests",
        "socket",
        "urllib",
    }
    forbidden_targets = {
        "app.integrations.gis",
        "app.integrations.satellite",
        "app.integrations.weather",
    }

    imports: set[str] = set()
    absolute_targets: set[str] = set()
    for source_path in package.glob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split(".", 1)[0])
                    absolute_targets.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imports.add(node.module.split(".", 1)[0])
                absolute_targets.add(node.module)

    assert imports.isdisjoint(forbidden_roots)
    assert absolute_targets.isdisjoint(forbidden_targets)
