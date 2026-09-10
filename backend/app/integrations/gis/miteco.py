"""Bounded official-data adapter for the MITECO OGC API Features service."""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import math
import time
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import quote, urlsplit
from uuid import UUID

import httpx

from app.core.integration import (
    IntegrationFailure,
    IntegrationResult,
    RetryPolicy,
    TimeoutPolicy,
    sanitize_integration_message,
)
from app.core.references import ExternalReference
from app.modules.assets.ports import (
    GISFeatureDescriptor,
    GISLayerQuery,
    GISLayerResult,
)

from .miteco_catalog import (
    MITECO_OGC_FEATURES_BASE_URL,
    MITECO_REUSE_NOTICE_URL,
    MITECO_SPAIN_CRS84_BBOX,
    MitecoCollection,
    get_miteco_collection,
)


_ALLOWED_CONTENT_TYPES = frozenset({"application/geo+json", "application/json"})
_GEOJSON_GEOMETRY_TYPES = frozenset(
    {
        "Point",
        "MultiPoint",
        "LineString",
        "MultiLineString",
        "Polygon",
        "MultiPolygon",
        "GeometryCollection",
    }
)
_MAX_FEATURE_REFERENCE_LENGTH = 512
_MAX_PROPERTY_KEYS = 500
_MAX_PROPERTY_DEPTH = 8
_MAX_PROPERTY_NODES = 2_000
_MAX_PROPERTY_STRING_LENGTH = 4_096
_MAX_GEOMETRY_DEPTH = 8
_DEFAULT_REQUEST_LIMIT = 25
_CRS84 = "OGC:CRS84"
_CONTEXT_DISCLAIMER = (
    "Official GIS context does not establish diagnosis, causation, or an "
    "authoritative GeoVision measurement."
)


class _ProviderPayloadError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_base_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    expected = urlsplit(MITECO_OGC_FEATURES_BASE_URL)
    if (
        parsed.scheme.lower() != "https"
        or parsed.hostname != expected.hostname
        or parsed.port not in {None, 443}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/") != expected.path
    ):
        raise ValueError(
            "MITECO OGC Features must use the reviewed official HTTPS origin and path"
        )
    return MITECO_OGC_FEATURES_BASE_URL


def _retry_after_seconds(value: str | None, *, now: datetime) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value.strip()))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0.0, (parsed.astimezone(timezone.utc) - now).total_seconds())


def _bbox(value: Any) -> tuple[float, float, float, float]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
        or len(value) != 4
        or any(isinstance(item, bool) for item in value)
    ):
        raise ValueError("GIS bbox must contain four numeric CRS84 coordinates")
    try:
        west, south, east, north = (float(item) for item in value)
    except (TypeError, ValueError) as exc:
        raise ValueError("GIS bbox must contain four numeric CRS84 coordinates") from exc
    if not all(math.isfinite(item) for item in (west, south, east, north)):
        raise ValueError("GIS bbox coordinates must be finite")
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("GIS bbox is outside CRS84 or has invalid bounds")
    return west, south, east, north


def _intersects(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> bool:
    return not (
        left[2] <= right[0]
        or left[0] >= right[2]
        or left[3] <= right[1]
        or left[1] >= right[3]
    )


def _format_coordinate(value: float) -> str:
    return format(value, ".12g")


def _position(value: Any) -> tuple[float, ...]:
    if (
        not isinstance(value, list)
        or len(value) not in {2, 3}
        or any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value)
    ):
        raise _ProviderPayloadError(
            "invalid_geojson",
            "MITECO returned an invalid GeoJSON position",
        )
    parsed = tuple(float(item) for item in value)
    if not all(math.isfinite(item) for item in parsed):
        raise _ProviderPayloadError(
            "invalid_geojson",
            "MITECO returned a non-finite GeoJSON coordinate",
        )
    if not (-180 <= parsed[0] <= 180 and -90 <= parsed[1] <= 90):
        raise _ProviderPayloadError(
            "invalid_geojson",
            "MITECO returned coordinates outside CRS84",
        )
    return parsed


def _positions(value: Any, *, minimum: int) -> tuple[tuple[float, ...], ...]:
    if not isinstance(value, list) or len(value) < minimum:
        raise _ProviderPayloadError(
            "invalid_geojson",
            "MITECO returned an invalid GeoJSON coordinate sequence",
        )
    return tuple(_position(item) for item in value)


def _line(value: Any) -> tuple[tuple[float, ...], ...]:
    return _positions(value, minimum=2)


def _ring(value: Any) -> tuple[tuple[float, ...], ...]:
    positions = _positions(value, minimum=4)
    if positions[0] != positions[-1]:
        raise _ProviderPayloadError(
            "invalid_geojson",
            "MITECO returned an open GeoJSON linear ring",
        )
    return positions


def _polygon(value: Any) -> None:
    if not isinstance(value, list) or not value:
        raise _ProviderPayloadError(
            "invalid_geojson",
            "MITECO returned an invalid GeoJSON polygon",
        )
    for ring in value:
        _ring(ring)


def _validate_geometry(value: Any, *, depth: int = 0) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise _ProviderPayloadError(
            "invalid_geojson",
            "MITECO returned a feature with an invalid geometry",
        )
    geometry_type = value.get("type")
    if geometry_type not in _GEOJSON_GEOMETRY_TYPES:
        raise _ProviderPayloadError(
            "invalid_geojson",
            "MITECO returned a feature with an unsupported geometry type",
        )
    if geometry_type == "GeometryCollection":
        geometries = value.get("geometries")
        if not isinstance(geometries, list) or depth >= _MAX_GEOMETRY_DEPTH:
            raise _ProviderPayloadError(
                "invalid_geojson",
                "MITECO returned an invalid GeoJSON GeometryCollection",
            )
        for geometry in geometries:
            _validate_geometry(geometry, depth=depth + 1)
    else:
        coordinates = value.get("coordinates")
        if geometry_type == "Point":
            _position(coordinates)
        elif geometry_type == "MultiPoint":
            _positions(coordinates, minimum=1)
        elif geometry_type == "LineString":
            _line(coordinates)
        elif geometry_type == "MultiLineString":
            if not isinstance(coordinates, list) or not coordinates:
                raise _ProviderPayloadError(
                    "invalid_geojson",
                    "MITECO returned an invalid GeoJSON MultiLineString",
                )
            for line in coordinates:
                _line(line)
        elif geometry_type == "Polygon":
            _polygon(coordinates)
        elif geometry_type == "MultiPolygon":
            if not isinstance(coordinates, list) or not coordinates:
                raise _ProviderPayloadError(
                    "invalid_geojson",
                    "MITECO returned an invalid GeoJSON MultiPolygon",
                )
            for polygon in coordinates:
                _polygon(polygon)
    return dict(value)


def _feature_bbox(value: Any) -> tuple[float, ...]:
    if value is None:
        return ()
    if (
        not isinstance(value, list)
        or len(value) not in {4, 6}
        or any(isinstance(item, bool) for item in value)
    ):
        raise _ProviderPayloadError(
            "invalid_geojson",
            "MITECO returned a feature with an invalid bbox",
        )
    try:
        parsed = tuple(float(item) for item in value)
    except (TypeError, ValueError) as exc:
        raise _ProviderPayloadError(
            "invalid_geojson",
            "MITECO returned a feature with a non-numeric bbox",
        ) from exc
    if not all(math.isfinite(item) for item in parsed):
        raise _ProviderPayloadError(
            "invalid_geojson",
            "MITECO returned a feature with a non-finite bbox",
        )
    if len(parsed) == 4:
        west, south, east, north = parsed
        valid = -180 <= west <= east <= 180 and -90 <= south <= north <= 90
    else:
        west, south, bottom, east, north, top = parsed
        valid = (
            -180 <= west <= east <= 180
            and -90 <= south <= north <= 90
            and bottom <= top
        )
    if not valid:
        raise _ProviderPayloadError(
            "invalid_geojson",
            "MITECO returned a feature bbox outside CRS84 or with invalid bounds",
        )
    return parsed


def _validate_json_value(
    value: Any,
    *,
    depth: int = 0,
    nodes: list[int] | None = None,
) -> None:
    budget = [0] if nodes is None else nodes
    budget[0] += 1
    if budget[0] > _MAX_PROPERTY_NODES or depth > _MAX_PROPERTY_DEPTH:
        raise _ProviderPayloadError(
            "properties_out_of_bounds",
            "MITECO returned feature properties with excessive complexity",
        )
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, str):
        if len(value) > _MAX_PROPERTY_STRING_LENGTH:
            raise _ProviderPayloadError(
                "properties_out_of_bounds",
                "MITECO returned a feature property string outside configured bounds",
            )
        return
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise _ProviderPayloadError(
                "invalid_geojson",
                "MITECO returned a non-finite feature property",
            )
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item, depth=depth + 1, nodes=budget)
        return
    if isinstance(value, Mapping):
        if len(value) > _MAX_PROPERTY_KEYS or any(
            not isinstance(key, str) or len(key) > 256 for key in value
        ):
            raise _ProviderPayloadError(
                "properties_out_of_bounds",
                "MITECO returned feature properties outside configured bounds",
            )
        for item in value.values():
            _validate_json_value(item, depth=depth + 1, nodes=budget)
        return
    raise _ProviderPayloadError(
        "invalid_geojson",
        "MITECO returned a non-JSON feature property",
    )


class MitecoOgcFeaturesProvider:
    """Read reviewed public MITECO features without promoting their authority."""

    adapter_version = "geovision-miteco-ogc-features-v1.0.0"
    provider_name = "miteco"

    def __init__(
        self,
        *,
        base_url: str = MITECO_OGC_FEATURES_BASE_URL,
        timeout_policy: TimeoutPolicy | None = None,
        retry_policy: RetryPolicy | None = None,
        max_features: int = 100,
        max_response_bytes: int = 2 * 1024 * 1024,
        client: httpx.Client | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = _now_utc,
    ) -> None:
        self.base_url = _canonical_base_url(base_url)
        if not 1 <= max_features <= 100:
            raise ValueError("MITECO maximum feature count must be between 1 and 100")
        if not 1024 <= max_response_bytes <= 16 * 1024 * 1024:
            raise ValueError(
                "MITECO maximum response size must be between 1 KiB and 16 MiB"
            )
        self.timeout_policy = timeout_policy or TimeoutPolicy()
        self.retry_policy = retry_policy or RetryPolicy()
        self.max_features = max_features
        self.max_response_bytes = max_response_bytes
        self.sleeper = sleeper
        self.clock = clock
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(
                connect=self.timeout_policy.connect_seconds,
                read=self.timeout_policy.read_seconds,
                write=self.timeout_policy.write_seconds,
                pool=self.timeout_policy.pool_seconds,
            ),
            follow_redirects=False,
            headers={
                "Accept": "application/geo+json, application/json",
                "User-Agent": "GeoVision-MITECO-Adapter/1.0",
            },
        )

    @staticmethod
    def _request(value: GISLayerQuery | Mapping[str, Any]) -> GISLayerQuery:
        if isinstance(value, GISLayerQuery):
            raw_internal_id: Any = value.internal_id
            raw_collection: Any = value.collection_key
            raw_bbox: Any = value.bbox
            raw_limit: Any = value.limit
            raw_crs: Any = value.crs
        elif isinstance(value, Mapping):
            raw_internal_id = value.get("internal_id")
            raw_collection = value.get("collection_key", value.get("collection"))
            raw_bbox = value.get("bbox")
            raw_limit = value.get("limit", _DEFAULT_REQUEST_LIMIT)
            raw_crs = value.get("crs", _CRS84)
        else:
            raise ValueError("GIS query must be a typed request or mapping")
        try:
            internal_id = UUID(str(raw_internal_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("GIS query requires a GeoVision internal_id UUID") from exc
        if not isinstance(raw_collection, str) or not raw_collection.strip():
            raise ValueError("GIS query requires a reviewed collection key")
        if isinstance(raw_limit, bool):
            raise ValueError("GIS result limit must be an integer")
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError) as exc:
            raise ValueError("GIS result limit must be an integer") from exc
        crs = str(raw_crs or "").strip().upper()
        if crs != _CRS84:
            raise ValueError("MITECO GIS queries require OGC:CRS84 bbox coordinates")
        return GISLayerQuery(
            internal_id=internal_id,
            collection_key=raw_collection.strip().lower().replace("-", "_"),
            bbox=_bbox(raw_bbox),
            limit=limit,
            crs=_CRS84,
        )

    def _read_body(self, response: httpx.Response) -> bytes:
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0]
        if content_type.strip().lower() not in _ALLOWED_CONTENT_TYPES:
            raise _ProviderPayloadError(
                "invalid_content_type",
                "MITECO returned an unsupported response content type",
            )
        content_length = response.headers.get("Content-Length")
        if content_length:
            try:
                parsed_content_length = int(content_length)
            except ValueError:
                parsed_content_length = None
            if (
                parsed_content_length is not None
                and parsed_content_length > self.max_response_bytes
            ):
                raise _ProviderPayloadError(
                    "response_too_large",
                    "MITECO response exceeds the configured byte limit",
                )
        body = bytearray()
        for chunk in response.iter_bytes():
            if len(body) + len(chunk) > self.max_response_bytes:
                raise _ProviderPayloadError(
                    "response_too_large",
                    "MITECO response exceeds the configured byte limit",
                )
            body.extend(chunk)
        return bytes(body)

    def _http_failure(
        self,
        status_code: int,
        *,
        retry_after_seconds: float | None,
    ) -> IntegrationFailure:
        if 300 <= status_code < 400:
            return IntegrationFailure(
                code="provider_redirect_rejected",
                message="MITECO attempted to redirect the bounded GIS request",
            )
        if status_code == 429:
            return IntegrationFailure(
                code="rate_limited",
                message="MITECO rate-limited the GIS request",
                retryable=True,
                retry_after_seconds=retry_after_seconds,
            )
        if status_code >= 500:
            return IntegrationFailure(
                code="provider_unavailable",
                message="MITECO is temporarily unavailable",
                retryable=True,
                retry_after_seconds=retry_after_seconds,
            )
        return IntegrationFailure(
            code=f"provider_http_{status_code}",
            message="MITECO rejected the GIS request",
        )

    def _fetch_items(
        self,
        *,
        url: str,
        params: Mapping[str, str],
    ) -> tuple[bytes | None, int, IntegrationFailure | None]:
        last_failure: IntegrationFailure | None = None
        for attempt in range(1, self.retry_policy.max_attempts + 1):
            try:
                with self.client.stream(
                    "GET",
                    url,
                    params=dict(params),
                    follow_redirects=False,
                ) as response:
                    if response.status_code == 200:
                        return self._read_body(response), attempt, None
                    retry_after = _retry_after_seconds(
                        response.headers.get("Retry-After"),
                        now=self.clock(),
                    )
                    last_failure = self._http_failure(
                        response.status_code,
                        retry_after_seconds=retry_after,
                    )
            except _ProviderPayloadError as exc:
                return None, attempt, IntegrationFailure(
                    code=exc.code,
                    message=str(exc),
                )
            except httpx.TimeoutException:
                last_failure = IntegrationFailure(
                    code="timeout",
                    message="MITECO GIS request timed out",
                    retryable=True,
                )
            except httpx.HTTPError:
                last_failure = IntegrationFailure(
                    code="provider_unreachable",
                    message="MITECO GIS request could not reach the official service",
                    retryable=True,
                )
            if last_failure is None or not self.retry_policy.allows_retry(
                attempts_made=attempt,
                failure=last_failure,
                operation_is_idempotent=True,
            ):
                return None, attempt, last_failure
            self.sleeper(
                self.retry_policy.delay_after(
                    attempt,
                    retry_after_seconds=last_failure.retry_after_seconds,
                )
            )
        return None, self.retry_policy.max_attempts, last_failure

    @staticmethod
    def _response_crs(body: Mapping[str, Any]) -> str:
        raw_crs = body.get("crs")
        if raw_crs is None:
            return _CRS84
        if not isinstance(raw_crs, Mapping):
            raise _ProviderPayloadError(
                "invalid_geojson",
                "MITECO returned invalid CRS metadata",
            )
        properties = raw_crs.get("properties")
        name = properties.get("name") if isinstance(properties, Mapping) else None
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise _ProviderPayloadError(
                "invalid_geojson",
                "MITECO returned invalid CRS metadata",
            )
        normalized = name.strip().lower()
        if normalized not in {
            "urn:ogc:def:crs:ogc::crs84",
            "urn:ogc:def:crs:ogc:1.3:crs84",
            "http://www.opengis.net/def/crs/ogc/1.3/crs84",
            "https://www.opengis.net/def/crs/ogc/1.3/crs84",
        }:
            raise _ProviderPayloadError(
                "unsupported_response_crs",
                "MITECO returned a CRS that GeoVision does not reproject",
            )
        return _CRS84

    @staticmethod
    def _common_provenance(
        *,
        collection: MitecoCollection,
        query: GISLayerQuery,
        items_url: str,
        fetched_at: datetime,
        response_timestamp: str | None,
        response_crs: str,
        response_bbox: tuple[float, ...],
    ) -> dict[str, Any]:
        return {
            "provider": (
                "Ministerio para la Transición Ecológica y el Reto Demográfico "
                "(MITECO)"
            ),
            "adapter_version": MitecoOgcFeaturesProvider.adapter_version,
            "protocol": "OGC API Features 1.0",
            "collection_key": collection.key,
            "collection_id": collection.collection_id,
            "collection_title": collection.title,
            "canonical_source_url": items_url,
            "metadata_url": collection.metadata_url,
            "license_id": collection.license_id,
            "license_url": collection.license_url,
            "attribution": collection.attribution,
            "reuse_notice_url": MITECO_REUSE_NOTICE_URL,
            "no_endorsement": True,
            "geographic_scope": collection.geographic_scope,
            "query_bbox": query.bbox,
            "query_crs": query.crs,
            "response_crs": response_crs,
            "response_bbox": response_bbox or None,
            "fetched_at": fetched_at.astimezone(timezone.utc).isoformat(),
            "provider_response_timestamp": response_timestamp,
            "official_source": True,
            "measurements_authoritative": False,
            "diagnostic_authority": False,
            "context_only": True,
            "disclaimer": _CONTEXT_DISCLAIMER,
        }

    @staticmethod
    def _features(
        raw_features: list[Any],
        *,
        common_provenance: Mapping[str, Any],
    ) -> tuple[GISFeatureDescriptor, ...]:
        features: list[GISFeatureDescriptor] = []
        for raw in raw_features:
            if not isinstance(raw, Mapping) or raw.get("type") != "Feature":
                raise _ProviderPayloadError(
                    "invalid_geojson",
                    "MITECO returned an invalid GeoJSON feature",
                )
            raw_reference = raw.get("id")
            if isinstance(raw_reference, bool) or not isinstance(
                raw_reference, (str, int)
            ):
                raise _ProviderPayloadError(
                    "invalid_geojson",
                    "MITECO returned a feature without a stable external reference",
                )
            reference = str(raw_reference).strip()
            if (
                not reference
                or len(reference) > _MAX_FEATURE_REFERENCE_LENGTH
                or any(ord(character) < 32 for character in reference)
            ):
                raise _ProviderPayloadError(
                    "invalid_geojson",
                    "MITECO returned an invalid external feature reference",
                )
            raw_properties = raw.get("properties")
            if raw_properties is None:
                properties: Mapping[str, Any] = {}
            elif isinstance(raw_properties, Mapping):
                if len(raw_properties) > _MAX_PROPERTY_KEYS or any(
                    not isinstance(key, str) or len(key) > 256
                    for key in raw_properties
                ):
                    raise _ProviderPayloadError(
                        "invalid_geojson",
                        "MITECO returned feature properties outside configured bounds",
                    )
                properties = dict(raw_properties)
                _validate_json_value(properties)
            else:
                raise _ProviderPayloadError(
                    "invalid_geojson",
                    "MITECO returned invalid GeoJSON feature properties",
                )
            provenance = dict(common_provenance)
            provenance["provider_feature_reference"] = reference
            features.append(
                GISFeatureDescriptor(
                    provider_reference=reference,
                    geometry=_validate_geometry(raw.get("geometry")),
                    properties=properties,
                    bbox=_feature_bbox(raw.get("bbox")),
                    provenance=provenance,
                )
            )
        return tuple(features)

    def query_layers(
        self,
        request: GISLayerQuery | Mapping[str, Any],
    ) -> IntegrationResult[GISLayerResult | Mapping[str, Any]]:
        operation = "query_layers"
        attempts = 1
        try:
            query = self._request(request)
            collection = get_miteco_collection(query.collection_key)
            if collection is None:
                return IntegrationResult.failed(
                    provider=self.provider_name,
                    operation=operation,
                    failure=IntegrationFailure(
                        code="unsupported_collection",
                        message="MITECO collection is not in the reviewed GeoVision manifest",
                    ),
                )
            if not 1 <= query.limit <= self.max_features:
                return IntegrationResult.failed(
                    provider=self.provider_name,
                    operation=operation,
                    failure=IntegrationFailure(
                        code="invalid_request",
                        message=(
                            "MITECO result limit must be between 1 and the configured "
                            "maximum"
                        ),
                    ),
                )
            if not _intersects(query.bbox, MITECO_SPAIN_CRS84_BBOX) or not _intersects(
                query.bbox, collection.extent
            ):
                return IntegrationResult.failed(
                    provider=self.provider_name,
                    operation=operation,
                    failure=IntegrationFailure(
                        code="coverage_mismatch",
                        message="MITECO official GIS coverage does not include this bbox",
                    ),
                )
            encoded_id = quote(collection.collection_id, safe="")
            items_url = f"{self.base_url}/collections/{encoded_id}/items"
            params = {
                "f": "application/geo+json",
                "bbox": ",".join(_format_coordinate(value) for value in query.bbox),
                "limit": str(query.limit),
            }
            body_bytes, attempts, failure = self._fetch_items(
                url=items_url,
                params=params,
            )
            if failure is not None or body_bytes is None:
                return IntegrationResult.failed(
                    provider=self.provider_name,
                    operation=operation,
                    failure=failure
                    or IntegrationFailure(
                        code="provider_unreachable",
                        message="MITECO GIS request did not return a response",
                        retryable=True,
                    ),
                    attempts=attempts,
                )
            try:
                body = json.loads(body_bytes.decode("utf-8"))
            except (
                UnicodeDecodeError,
                json.JSONDecodeError,
                RecursionError,
                ValueError,
            ) as exc:
                raise _ProviderPayloadError(
                    "invalid_geojson",
                    "MITECO returned malformed GeoJSON",
                ) from exc
            if not isinstance(body, Mapping) or body.get("type") != "FeatureCollection":
                raise _ProviderPayloadError(
                    "invalid_geojson",
                    "MITECO returned an invalid GeoJSON FeatureCollection",
                )
            raw_features = body.get("features")
            if not isinstance(raw_features, list):
                raise _ProviderPayloadError(
                    "invalid_geojson",
                    "MITECO returned an invalid GeoJSON feature list",
                )
            if len(raw_features) > query.limit:
                raise _ProviderPayloadError(
                    "feature_limit_exceeded",
                    "MITECO returned features outside the requested result bound",
                )
            number_returned = body.get("numberReturned")
            if (
                number_returned is not None
                and (
                    isinstance(number_returned, bool)
                    or not isinstance(number_returned, int)
                    or number_returned != len(raw_features)
                )
            ):
                raise _ProviderPayloadError(
                    "invalid_geojson",
                    "MITECO returned inconsistent feature-count metadata",
                )
            response_timestamp = body.get("timeStamp")
            if response_timestamp is not None and (
                not isinstance(response_timestamp, str)
                or not response_timestamp.strip()
                or len(response_timestamp) > 100
            ):
                raise _ProviderPayloadError(
                    "invalid_geojson",
                    "MITECO returned invalid response timestamp metadata",
                )
            response_crs = self._response_crs(body)
            response_bbox = _feature_bbox(body.get("bbox"))
            common_provenance = self._common_provenance(
                collection=collection,
                query=query,
                items_url=items_url,
                fetched_at=self.clock(),
                response_timestamp=(
                    response_timestamp.strip()
                    if isinstance(response_timestamp, str)
                    else None
                ),
                response_crs=response_crs,
                response_bbox=response_bbox,
            )
            features = self._features(
                raw_features,
                common_provenance=common_provenance,
            )
            return IntegrationResult.succeeded(
                provider=self.provider_name,
                operation=operation,
                value=GISLayerResult(
                    collection_key=collection.key,
                    provider_collection_id=collection.collection_id,
                    title=collection.title,
                    features=features,
                    bbox=query.bbox,
                    crs=response_crs,
                    provenance=common_provenance,
                ),
                external_reference=ExternalReference(
                    internal_id=query.internal_id,
                    provider=self.provider_name,
                    resource_type="gis_layer_collection",
                    value=collection.collection_id,
                ),
                attempts=attempts,
            )
        except _ProviderPayloadError as exc:
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation=operation,
                failure=IntegrationFailure(code=exc.code, message=str(exc)),
                attempts=attempts,
            )
        except (TypeError, ValueError) as exc:
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation=operation,
                failure=IntegrationFailure(
                    code="invalid_request",
                    message=sanitize_integration_message(exc),
                ),
            )


__all__ = ["MitecoOgcFeaturesProvider"]
