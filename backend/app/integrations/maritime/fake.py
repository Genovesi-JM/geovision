"""Deterministic maritime contract fixture for local and test environments."""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Mapping
import uuid

from app.core.integration import (
    IntegrationFailure,
    IntegrationResult,
    IntegrationStatus,
)
from app.core.references import ExternalReference
from app.modules.monitoring.ports import (
    MaritimeContextReading,
    MaritimeContextRequest,
    MaritimeContextResult,
    MaritimeSourceKind,
)


_FIXTURE_TIME = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
_MAX_DISTANCE_KM = 1_000.0
_MAX_RESULTS = 500


def _bounded_float(
    value: object,
    *,
    field_name: str,
    minimum: float,
    maximum: float,
    include_minimum: bool = True,
) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a finite number")
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a finite number") from exc
    lower_ok = result >= minimum if include_minimum else result > minimum
    if not math.isfinite(result) or not lower_ok or result > maximum:
        raise ValueError(f"{field_name} is outside the supported bounds")
    return result


def _utc_datetime(value: object, *, field_name: str) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        candidate = value.strip()
        if candidate.endswith("Z"):
            candidate = f"{candidate[:-1]}+00:00"
        try:
            value = datetime.fromisoformat(candidate)
        except ValueError as exc:
            raise ValueError(f"{field_name} must be an ISO-8601 datetime") from exc
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be an ISO-8601 datetime")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _bounded_limit(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        result = value
    elif isinstance(value, str) and value.strip().isdigit():
        result = int(value.strip())
    else:
        raise ValueError("limit must be an integer between 1 and 500")
    if not 1 <= result <= _MAX_RESULTS:
        raise ValueError("limit must be an integer between 1 and 500")
    return result


class DeterministicMaritimeProvider:
    """Exercise normalization without simulating vendor or navigational truth."""

    provider_name = "fake"
    adapter_version = "geovision-deterministic-maritime-v1"

    @staticmethod
    def _request(
        request: MaritimeContextRequest | Mapping[str, Any],
    ) -> tuple[uuid.UUID, float, float, datetime | None, datetime | None, float, int]:
        if isinstance(request, MaritimeContextRequest):
            raw_internal_id: object = request.internal_id
            raw_latitude: object = request.latitude
            raw_longitude: object = request.longitude
            raw_starts_at: object = request.starts_at
            raw_ends_at: object = request.ends_at
            raw_max_distance: object = request.max_distance_km
            raw_limit: object = request.limit
        elif isinstance(request, Mapping):
            raw_internal_id = request.get("internal_id")
            raw_latitude = request.get("latitude")
            raw_longitude = request.get("longitude")
            raw_starts_at = request.get("starts_at")
            raw_ends_at = request.get("ends_at")
            raw_max_distance = request.get("max_distance_km", 100.0)
            raw_limit = request.get("limit", 100)
        else:
            raise ValueError("maritime context requires a typed request or mapping")

        try:
            internal_id = uuid.UUID(str(raw_internal_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError(
                "maritime context requires a GeoVision internal_id UUID"
            ) from exc
        latitude = _bounded_float(
            raw_latitude,
            field_name="latitude",
            minimum=-90.0,
            maximum=90.0,
        )
        longitude = _bounded_float(
            raw_longitude,
            field_name="longitude",
            minimum=-180.0,
            maximum=180.0,
        )
        starts_at = _utc_datetime(raw_starts_at, field_name="starts_at")
        ends_at = _utc_datetime(raw_ends_at, field_name="ends_at")
        if starts_at is not None and ends_at is not None and starts_at > ends_at:
            raise ValueError("starts_at must not be later than ends_at")
        max_distance_km = _bounded_float(
            raw_max_distance,
            field_name="max_distance_km",
            minimum=0.0,
            maximum=_MAX_DISTANCE_KM,
            include_minimum=False,
        )
        limit = _bounded_limit(raw_limit)
        return (
            internal_id,
            latitude,
            longitude,
            starts_at,
            ends_at,
            max_distance_km,
            limit,
        )

    def operational_context(
        self,
        request: MaritimeContextRequest | Mapping[str, Any],
    ) -> IntegrationResult[MaritimeContextResult | Mapping[str, Any]]:
        operation = "operational_context"
        try:
            (
                internal_id,
                latitude,
                longitude,
                starts_at,
                ends_at,
                max_distance_km,
                limit,
            ) = self._request(request)
        except (TypeError, ValueError) as exc:
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation=operation,
                failure=IntegrationFailure(
                    code="invalid_request",
                    message=str(exc),
                ),
            )

        valid_at = ends_at or starts_at or _FIXTURE_TIME
        reference = "fixture-maritime-" + str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                (
                    "geovision:maritime:"
                    f"{internal_id}:{latitude:.6f}:{longitude:.6f}:"
                    f"{valid_at.isoformat()}"
                ),
            )
        )
        provenance = {
            "provider": "deterministic",
            "adapter_version": self.adapter_version,
            "fixture": True,
            "query_max_distance_km": max_distance_km,
        }
        readings = (
            MaritimeContextReading(
                provider_reference=f"{reference}:observed",
                valid_at=valid_at,
                station_reference="fixture-observation-station",
                latitude=latitude,
                longitude=longitude,
                metric="water_temperature",
                value=18.0,
                unit="degC",
                quality="simulated",
                source="geovision_contract_fixture",
                source_kind=MaritimeSourceKind.OBSERVED,
                license_id="GEOVISION-CONTRACT-FIXTURE",
                license_url=None,
                attribution=(
                    "GeoVision deterministic contract fixture; not operational data."
                ),
                provenance={**provenance, "source_kind": "observed"},
            ),
            MaritimeContextReading(
                provider_reference=f"{reference}:model",
                valid_at=valid_at,
                station_reference="fixture-model-point",
                latitude=latitude,
                longitude=longitude,
                metric="significant_wave_height",
                value=0.8,
                unit="m",
                quality="simulated",
                source="geovision_contract_fixture",
                source_kind=MaritimeSourceKind.MODEL,
                license_id="GEOVISION-CONTRACT-FIXTURE",
                license_url=None,
                attribution=(
                    "GeoVision deterministic contract fixture; not operational data."
                ),
                provenance={**provenance, "source_kind": "model"},
            ),
        )[:limit]
        return IntegrationResult(
            provider=self.provider_name,
            operation=operation,
            status=IntegrationStatus.SIMULATED,
            value=MaritimeContextResult(
                internal_id=internal_id,
                readings=readings,
            ),
            external_reference=ExternalReference(
                internal_id=internal_id,
                provider=self.provider_name,
                resource_type="maritime_context",
                value=reference,
            ),
        )


__all__ = ["DeterministicMaritimeProvider"]
