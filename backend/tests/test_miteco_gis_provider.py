"""Contract tests for bounded official MITECO GIS context."""

from __future__ import annotations

from datetime import datetime, timezone
import gzip
import json
from typing import Any, Callable
import uuid

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.integration import IntegrationStatus, RetryPolicy, TimeoutPolicy
from app.integrations.gis import MitecoOgcFeaturesProvider, create_gis_provider
from app.integrations.gis.fake import FakeGISProvider
from app.integrations.gis.miteco_catalog import (
    MITECO_ATTRIBUTION,
    MITECO_OGC_FEATURES_BASE_URL,
    MitecoCollection,
)
from app.modules.assets.ports import GISLayerQuery, GISLayerResult, GISProvider


COLLECTION_KEY = "biodiversity_priority_zones"
COLLECTION_ID = "costas:poem_uso_prio_biodiv_zupbd"
MADRID_BBOX = (-3.8, 40.3, -3.5, 40.6)
FIXED_NOW = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)


def _feature_collection(
    *,
    features: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    selected = (
        [
            {
                "type": "Feature",
                "id": "poem_biodiv.17",
                "bbox": [-3.7, 40.4, -3.6, 40.5],
                "geometry": {"type": "Point", "coordinates": [-3.65, 40.45]},
                "properties": {"category": "official context"},
            }
        ]
        if features is None
        else features
    )
    return {
        "type": "FeatureCollection",
        "bbox": [-3.7, 40.4, -3.6, 40.5],
        "timeStamp": "2026-09-09T08:00:00Z",
        "numberReturned": len(selected),
        "features": selected,
    }


def _request(*, limit: int = 25) -> GISLayerQuery:
    return GISLayerQuery(
        internal_id=uuid.uuid4(),
        collection_key=COLLECTION_KEY,
        bbox=MADRID_BBOX,
        limit=limit,
    )


def _provider(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    retry_policy: RetryPolicy | None = None,
    max_features: int = 100,
    max_response_bytes: int = 2 * 1024 * 1024,
    sleeper: Callable[[float], None] = lambda _delay: None,
    follow_redirects: bool = False,
) -> MitecoOgcFeaturesProvider:
    return MitecoOgcFeaturesProvider(
        client=httpx.Client(
            transport=httpx.MockTransport(handler),
            follow_redirects=follow_redirects,
        ),
        retry_policy=retry_policy,
        max_features=max_features,
        max_response_bytes=max_response_bytes,
        sleeper=sleeper,
        clock=lambda: FIXED_NOW,
    )


def test_success_uses_fixed_encoded_path_and_preserves_official_provenance() -> None:
    internal_id = uuid.uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.host == "gis.miteco.gob.es"
        assert request.url.raw_path.split(b"?", 1)[0] == (
            b"/geoserver/ogc/features/v1/collections/"
            b"costas%3Apoem_uso_prio_biodiv_zupbd/items"
        )
        assert request.url.params["f"] == "application/geo+json"
        assert request.url.params["bbox"] == "-3.8,40.3,-3.5,40.6"
        assert request.url.params["limit"] == "7"
        return httpx.Response(
            200,
            json=_feature_collection(),
            headers={"Content-Type": "application/geo+json; charset=utf-8"},
        )

    result = _provider(handler).query_layers(
        {
            "internal_id": internal_id,
            "collection": "biodiversity-priority-zones",
            "bbox": list(MADRID_BBOX),
            "limit": 7,
        }
    )

    assert result.status is IntegrationStatus.SUCCEEDED
    assert result.attempts == 1
    assert result.external_reference is not None
    assert result.external_reference.internal_id == internal_id
    assert result.external_reference.value == COLLECTION_ID
    assert isinstance(result.value, GISLayerResult)
    layer = result.value
    assert layer.provider_collection_id == COLLECTION_ID
    assert layer.measurements_authoritative is False
    assert layer.diagnostic_authority is False
    assert layer.context_only is True
    assert len(layer.features) == 1
    assert layer.features[0].provider_reference == "poem_biodiv.17"
    assert layer.features[0].properties == {"category": "official context"}
    for provenance in (layer.provenance, layer.features[0].provenance):
        assert provenance["attribution"] == MITECO_ATTRIBUTION
        assert provenance["attribution"] == (
            "Origen de los datos: Ministerio para la Transición ecológica y el "
            "Reto Demográfico"
        )
        assert provenance["license_id"] == "MITECO-GENERAL-REUSE-CONDITIONS"
        assert provenance["license_url"] == provenance["reuse_notice_url"]
        assert provenance["no_endorsement"] is True
        assert provenance["official_source"] is True
        assert provenance["measurements_authoritative"] is False
        assert provenance["diagnostic_authority"] is False
        assert provenance["context_only"] is True
        assert "diagnosis" in provenance["disclaimer"]
        assert "?" not in provenance["canonical_source_url"]
        assert provenance["provider_response_timestamp"] == (
            "2026-09-09T08:00:00Z"
        )
        assert provenance["response_bbox"] == (-3.7, 40.4, -3.6, 40.5)
        assert provenance["fetched_at"] == "2026-09-10T12:00:00+00:00"


def test_collection_urls_use_standards_based_percent_encoding() -> None:
    collection = MitecoCollection(
        key="encoding_test",
        collection_id="workspace:layer name/ü",
        title="Encoding test",
        description="Test-only metadata value",
        metadata_url="https://example.invalid/metadata",
        license_id="test",
        license_url="https://example.invalid/license",
    )

    assert collection.collection_url.endswith(
        "/collections/workspace%3Alayer%20name%2F%C3%BC"
    )


def test_typed_request_and_empty_feature_collection_are_valid_context() -> None:
    provider = _provider(
        lambda _request: httpx.Response(
            200,
            json=_feature_collection(features=[]),
            headers={"Content-Type": "application/json"},
        )
    )

    result = provider.query_layers(_request())

    assert result.ok
    assert isinstance(result.value, GISLayerResult)
    assert result.value.features == ()
    assert result.value.measurements_authoritative is False


def test_existing_contract_fake_accepts_typed_and_legacy_gis_queries() -> None:
    internal_id = uuid.uuid4()
    provider = FakeGISProvider()

    typed = provider.query_layers(
        GISLayerQuery(
            internal_id=internal_id,
            collection_key=COLLECTION_KEY,
            bbox=MADRID_BBOX,
        )
    )
    legacy = provider.query_layers({"internal_id": internal_id})

    assert typed.status is IntegrationStatus.SIMULATED
    assert legacy.status is IntegrationStatus.SIMULATED
    assert typed.external_reference == legacy.external_reference


@pytest.mark.parametrize(
    ("query_input", "expected_code"),
    (
        ({"collection_key": COLLECTION_KEY, "bbox": MADRID_BBOX}, "invalid_request"),
        (
            {
                "internal_id": "not-a-uuid",
                "collection_key": COLLECTION_KEY,
                "bbox": MADRID_BBOX,
            },
            "invalid_request",
        ),
        (
            {
                "internal_id": uuid.uuid4(),
                "collection_key": "not_reviewed",
                "bbox": MADRID_BBOX,
            },
            "unsupported_collection",
        ),
        (
            {
                "internal_id": uuid.uuid4(),
                "collection_key": COLLECTION_KEY,
                "bbox": (13.0, -9.0, 14.0, -8.0),
            },
            "coverage_mismatch",
        ),
        (
            {
                "internal_id": uuid.uuid4(),
                "collection_key": COLLECTION_KEY,
                "bbox": MADRID_BBOX,
                "crs": "EPSG:4326",
            },
            "invalid_request",
        ),
        (
            {
                "internal_id": uuid.uuid4(),
                "collection_key": COLLECTION_KEY,
                "bbox": MADRID_BBOX,
                "limit": 101,
            },
            "invalid_request",
        ),
    ),
)
def test_invalid_scope_fails_before_network(
    query_input: dict[str, Any],
    expected_code: str,
) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise AssertionError("invalid request must not reach MITECO")

    result = _provider(handler).query_layers(query_input)

    assert result.status is IntegrationStatus.FAILED
    assert result.failure is not None
    assert result.failure.code == expected_code
    assert calls == 0


@pytest.mark.parametrize(
    "base_url",
    (
        "http://gis.miteco.gob.es/geoserver/ogc/features/v1",
        "https://evil.example/geoserver/ogc/features/v1",
        "https://gis.miteco.gob.es/geoserver/ogc/features/v1/search",
        "https://user:password@gis.miteco.gob.es/geoserver/ogc/features/v1",
        "https://gis.miteco.gob.es/geoserver/ogc/features/v1?token=secret",
    ),
)
def test_provider_rejects_any_non_official_origin_or_path(base_url: str) -> None:
    with pytest.raises(ValueError, match="official HTTPS origin and path"):
        MitecoOgcFeaturesProvider(base_url=base_url)

    with pytest.raises(ValidationError, match="MITECO_OGC_FEATURES_BASE_URL"):
        Settings(_env_file=None, miteco_ogc_features_base_url=base_url)


def test_factory_builds_public_provider_with_shared_policies() -> None:
    config = Settings(
        _env_file=None,
        gis_provider="miteco",
        miteco_ogc_features_base_url=f"{MITECO_OGC_FEATURES_BASE_URL}/",
        miteco_gis_max_features=42,
        miteco_gis_max_response_bytes=4096,
        integration_connect_timeout_seconds=2.0,
        integration_read_timeout_seconds=11.0,
        integration_retry_attempts=4,
        integration_retry_initial_seconds=0.25,
        integration_retry_max_seconds=3.0,
    )

    provider = create_gis_provider(config)

    assert isinstance(provider, MitecoOgcFeaturesProvider)
    assert isinstance(provider, GISProvider)
    assert provider.base_url == MITECO_OGC_FEATURES_BASE_URL
    assert provider.timeout_policy == TimeoutPolicy(
        connect_seconds=2.0,
        read_seconds=11.0,
        write_seconds=11.0,
        pool_seconds=2.0,
    )
    assert provider.retry_policy.max_attempts == 4
    assert provider.max_features == 42
    assert provider.max_response_bytes == 4096
    assert config.safe_summary()["providers"]["gis"] == "miteco"
    assert config.safe_summary()["configured"]["miteco"] is True


def test_redirect_is_rejected_even_if_injected_client_follows_redirects() -> None:
    requested_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_hosts.append(str(request.url.host))
        return httpx.Response(
            302,
            headers={"Location": "https://untrusted.example/features?token=secret"},
        )

    result = _provider(handler, follow_redirects=True).query_layers(_request())

    assert result.status is IntegrationStatus.FAILED
    assert result.failure is not None
    assert result.failure.code == "provider_redirect_rejected"
    assert requested_hosts == ["gis.miteco.gob.es"]
    assert "untrusted" not in str(result)
    assert "secret" not in str(result)


def test_rate_limit_and_server_failures_retry_with_bounded_delays() -> None:
    statuses = iter((429, 503, 200))
    delays: list[float] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        status = next(statuses)
        if status == 200:
            return httpx.Response(
                200,
                json=_feature_collection(),
                headers={"Content-Type": "application/geo+json"},
            )
        headers = {"Retry-After": "1.5"} if status == 429 else {}
        return httpx.Response(status, headers=headers, content=b"not retained")

    provider = _provider(
        handler,
        retry_policy=RetryPolicy(
            max_attempts=3,
            initial_delay_seconds=0.25,
            max_delay_seconds=1.0,
        ),
        sleeper=delays.append,
    )

    result = provider.query_layers(_request())

    assert result.ok
    assert result.attempts == 3
    assert delays == [1.0, 0.5]


def test_timeout_retries_but_normal_client_error_does_not() -> None:
    timeout_calls = 0

    def timeout_then_success(request: httpx.Request) -> httpx.Response:
        nonlocal timeout_calls
        timeout_calls += 1
        if timeout_calls == 1:
            raise httpx.ReadTimeout("credential=must-not-appear", request=request)
        return httpx.Response(
            200,
            json=_feature_collection(),
            headers={"Content-Type": "application/json"},
        )

    retrying = _provider(
        timeout_then_success,
        retry_policy=RetryPolicy(
            max_attempts=2,
            initial_delay_seconds=0,
            max_delay_seconds=0,
        ),
    ).query_layers(_request())

    assert retrying.ok
    assert retrying.attempts == 2
    assert timeout_calls == 2

    client_calls = 0

    def rejected(_request: httpx.Request) -> httpx.Response:
        nonlocal client_calls
        client_calls += 1
        return httpx.Response(400, content=b"token=provider-body-secret")

    failed = _provider(rejected).query_layers(_request())

    assert failed.status is IntegrationStatus.FAILED
    assert failed.attempts == 1
    assert failed.failure is not None
    assert failed.failure.code == "provider_http_400"
    assert client_calls == 1
    assert "provider-body-secret" not in str(failed)


def test_transport_error_message_does_not_echo_exception_or_query_location() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadError(
            "token=transport-secret bbox=-3.8,40.3,-3.5,40.6",
            request=request,
        )

    result = _provider(
        handler,
        retry_policy=RetryPolicy(max_attempts=1),
    ).query_layers(_request())

    assert result.status is IntegrationStatus.FAILED
    assert result.failure is not None
    assert result.failure.code == "provider_unreachable"
    assert "transport-secret" not in str(result.failure)
    assert "-3.8" not in str(result.failure)


@pytest.mark.parametrize(
    ("response", "expected_code"),
    (
        (
            httpx.Response(
                200,
                content=b"<html>not geojson</html>",
                headers={"Content-Type": "text/html"},
            ),
            "invalid_content_type",
        ),
        (
            httpx.Response(
                200,
                content=b"{}",
                headers={
                    "Content-Type": "application/json",
                    "Content-Length": "2048",
                },
            ),
            "response_too_large",
        ),
        (
            httpx.Response(
                200,
                content=b"{" + (b" " * 1100) + b"}",
                headers={"Content-Type": "application/json"},
            ),
            "response_too_large",
        ),
        (
            httpx.Response(
                200,
                content=gzip.compress(b'{"padding":"' + (b"x" * 2048) + b'"}'),
                headers={
                    "Content-Type": "application/json",
                    "Content-Encoding": "gzip",
                },
            ),
            "response_too_large",
        ),
    ),
)
def test_content_type_and_compressed_or_streamed_size_fail_closed(
    response: httpx.Response,
    expected_code: str,
) -> None:
    result = _provider(
        lambda _request: response,
        max_response_bytes=1024,
    ).query_layers(_request())

    assert result.status is IntegrationStatus.FAILED
    assert result.failure is not None
    assert result.failure.code == expected_code


@pytest.mark.parametrize(
    ("body", "expected_code"),
    (
        ({"type": "FeatureCollection", "features": "not-a-list"}, "invalid_geojson"),
        (
            {
                "type": "FeatureCollection",
                "numberReturned": 2,
                "features": [_feature_collection()["features"][0]],
            },
            "invalid_geojson",
        ),
        (
            {
                "type": "FeatureCollection",
                "numberReturned": 1,
                "features": [
                    {
                        "type": "Feature",
                        "id": "bad-geometry",
                        "geometry": {"type": "Point", "coordinates": [False, 1]},
                        "properties": {},
                    }
                ],
            },
            "invalid_geojson",
        ),
        ({"type": "Feature", "features": []}, "invalid_geojson"),
    ),
)
def test_geojson_schema_and_counts_fail_closed(
    body: dict[str, Any],
    expected_code: str,
) -> None:
    result = _provider(
        lambda _request: httpx.Response(
            200,
            content=json.dumps(body).encode(),
            headers={"Content-Type": "application/geo+json"},
        )
    ).query_layers(_request(limit=1))

    assert result.status is IntegrationStatus.FAILED
    assert result.failure is not None
    assert result.failure.code == expected_code


@pytest.mark.parametrize(
    ("feature_patch", "expected_code"),
    (
        ({"bbox": [5, 45, -5, 40]}, "invalid_geojson"),
        (
            {
                "geometry": {
                    "type": "Point",
                    "coordinates": [250.0, 40.0],
                }
            },
            "invalid_geojson",
        ),
        (
            {
                "geometry": {
                    "type": "Point",
                    "coordinates": [[-3.65, 40.45]],
                }
            },
            "invalid_geojson",
        ),
        (
            {
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[-3.7, 40.4], [-3.6, 40.4], [-3.6, 40.5], [-3.7, 40.5]]
                    ],
                }
            },
            "invalid_geojson",
        ),
        (
            {"properties": {"description": "x" * 4097}},
            "properties_out_of_bounds",
        ),
    ),
)
def test_feature_spatial_and_property_bounds_fail_closed(
    feature_patch: dict[str, Any],
    expected_code: str,
) -> None:
    feature = dict(_feature_collection()["features"][0])
    feature.update(feature_patch)
    result = _provider(
        lambda _request: httpx.Response(
            200,
            json=_feature_collection(features=[feature]),
            headers={"Content-Type": "application/geo+json"},
        )
    ).query_layers(_request())

    assert result.status is IntegrationStatus.FAILED
    assert result.failure is not None
    assert result.failure.code == expected_code


def test_deeply_nested_property_values_fail_closed() -> None:
    nested: Any = "leaf"
    for _index in range(12):
        nested = {"next": nested}
    feature = dict(_feature_collection()["features"][0])
    feature["properties"] = {"nested": nested}

    result = _provider(
        lambda _request: httpx.Response(
            200,
            json=_feature_collection(features=[feature]),
            headers={"Content-Type": "application/json"},
        )
    ).query_layers(_request())

    assert result.status is IntegrationStatus.FAILED
    assert result.failure is not None
    assert result.failure.code == "properties_out_of_bounds"


def test_response_crs_is_limited_to_reviewed_crs84_equivalents() -> None:
    unsupported = _feature_collection()
    unsupported["crs"] = {
        "type": "name",
        "properties": {"name": "urn:ogc:def:crs:EPSG::4258"},
    }
    rejected = _provider(
        lambda _request: httpx.Response(
            200,
            json=unsupported,
            headers={"Content-Type": "application/json"},
        )
    ).query_layers(_request())

    assert rejected.status is IntegrationStatus.FAILED
    assert rejected.failure is not None
    assert rejected.failure.code == "unsupported_response_crs"

    accepted = _feature_collection()
    accepted["crs"] = {
        "type": "name",
        "properties": {
            "name": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"
        },
    }
    succeeded = _provider(
        lambda _request: httpx.Response(
            200,
            json=accepted,
            headers={"Content-Type": "application/json"},
        )
    ).query_layers(_request())

    assert succeeded.ok
    assert isinstance(succeeded.value, GISLayerResult)
    assert succeeded.value.crs == "OGC:CRS84"


def test_provider_never_uses_catalog_or_satellite_weather_client_endpoints() -> None:
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url.copy_with(query=None)))
        return httpx.Response(
            200,
            json=_feature_collection(),
            headers={"Content-Type": "application/json"},
        )

    result = _provider(handler).query_layers(_request())

    assert result.ok
    assert len(seen_urls) == 1
    assert seen_urls[0].startswith(MITECO_OGC_FEATURES_BASE_URL)
    assert "catalogo.datosabiertos" not in seen_urls[0]
    assert "copernicus" not in seen_urls[0]
    assert "aemet" not in seen_urls[0]
