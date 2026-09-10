"""AEMET OpenData current-observation adapter for Spanish assets."""

from __future__ import annotations

from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt
import time
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

import httpx

from app.core.integration import IntegrationFailure, IntegrationResult, sanitize_integration_message
from app.modules.monitoring.ports import (
    WeatherMetric,
    WeatherRequest,
    WeatherSnapshot,
)


_METRICS: dict[str, tuple[str, str]] = {
    "ta": ("air_temperature", "degC"),
    "tamin": ("air_temperature_min", "degC"),
    "tamax": ("air_temperature_max", "degC"),
    "tpr": ("dew_point_temperature", "degC"),
    "ts": ("ground_temperature", "degC"),
    "hr": ("relative_humidity", "%"),
    "prec": ("precipitation", "mm"),
    "vv": ("wind_speed", "m/s"),
    "vmax": ("wind_gust_speed", "m/s"),
    "dv": ("wind_direction", "degree"),
    "dmax": ("wind_gust_direction", "degree"),
    "pres": ("station_pressure", "hPa"),
    "pres_nmar": ("sea_level_pressure", "hPa"),
    "vis": ("visibility", "km"),
    "inso": ("sunshine_duration", "hour"),
    "nieve": ("snow_depth", "cm"),
}


def _number(value: Any) -> float | None:
    if isinstance(value, str):
        candidate = value.strip().replace(",", ".")
        if candidate.lower() in {"", "ip", "tr", "nan", "null"}:
            return 0.0 if candidate.lower() in {"ip", "tr"} else None
        value = candidate
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None


def _utc_naive(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _distance_km(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    lat1, lon1, lat2, lon2 = map(radians, (lat_a, lon_a, lat_b, lon_b))
    d_lat = lat2 - lat1
    d_lon = lon2 - lon1
    value = sin(d_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(d_lon / 2) ** 2
    return 6371.0088 * 2 * asin(min(1.0, sqrt(value)))


class AemetOpenDataProvider:
    adapter_version = "geovision-aemet-opendata-v1.0.0"
    provider_name = "aemet"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        connect_timeout_seconds: float = 5.0,
        read_timeout_seconds: float = 30.0,
        retry_attempts: int = 3,
        retry_initial_seconds: float = 0.5,
        retry_max_seconds: float = 8.0,
        client: httpx.Client | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.retry_attempts = retry_attempts
        self.retry_initial_seconds = retry_initial_seconds
        self.retry_max_seconds = retry_max_seconds
        self.sleeper = sleeper
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(
                connect=connect_timeout_seconds,
                read=read_timeout_seconds,
                write=read_timeout_seconds,
                pool=connect_timeout_seconds,
            ),
            follow_redirects=False,
            headers={"Accept": "application/json", "api_key": api_key},
        )

    @staticmethod
    def _request(value: WeatherRequest | Mapping[str, Any]) -> WeatherRequest:
        if isinstance(value, WeatherRequest):
            return value
        return WeatherRequest(
            latitude=float(value["latitude"]),
            longitude=float(value["longitude"]),
            starts_at=value.get("starts_at") if isinstance(value.get("starts_at"), datetime) else _utc_naive(value.get("starts_at")),
            ends_at=value.get("ends_at") if isinstance(value.get("ends_at"), datetime) else _utc_naive(value.get("ends_at")),
            max_distance_km=float(value.get("max_distance_km", 150.0)),
        )

    def _get(self, url: str) -> tuple[httpx.Response | None, int, Exception | None]:
        last_response: httpx.Response | None = None
        last_error: Exception | None = None
        for attempt in range(1, self.retry_attempts + 1):
            try:
                last_response = self.client.get(
                    url,
                    headers={"Accept": "application/json", "api_key": self.api_key},
                )
                if last_response.status_code < 500 and last_response.status_code != 429:
                    return last_response, attempt, None
            except httpx.HTTPError as exc:
                last_error = exc
            if attempt < self.retry_attempts:
                delay = min(
                    self.retry_initial_seconds * (2 ** (attempt - 1)),
                    self.retry_max_seconds,
                )
                if last_response is not None and last_response.status_code == 429:
                    try:
                        delay = min(float(last_response.headers.get("Retry-After", delay)), self.retry_max_seconds)
                    except ValueError:
                        pass
                self.sleeper(max(0.0, delay))
        return last_response, self.retry_attempts, last_error

    def _failure(
        self,
        *,
        operation: str,
        response: httpx.Response | None,
        attempts: int,
        error: Exception | None,
    ) -> IntegrationResult[tuple[WeatherSnapshot, ...]]:
        if response is None:
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation=operation,
                failure=IntegrationFailure(
                    "provider_unreachable",
                    sanitize_integration_message(error or "AEMET request failed", secret_values=(self.api_key,)),
                    retryable=True,
                ),
                attempts=attempts,
            )
        return IntegrationResult.failed(
            provider=self.provider_name,
            operation=operation,
            failure=IntegrationFailure(
                f"provider_http_{response.status_code}",
                "AEMET OpenData rejected the weather request",
                retryable=response.status_code == 429 or response.status_code >= 500,
            ),
            attempts=attempts,
        )

    def observations(
        self,
        request: WeatherRequest | Mapping[str, Any],
    ) -> IntegrationResult[tuple[WeatherSnapshot, ...]]:
        operation = "observations"
        try:
            normalized = self._request(request)
            if not (-90 <= normalized.latitude <= 90 and -180 <= normalized.longitude <= 180):
                raise ValueError("weather coordinates are outside EPSG:4326")
            if normalized.max_distance_km <= 0:
                raise ValueError("weather maximum station distance must be positive")
            response, attempts, error = self._get(
                f"{self.base_url}/api/observacion/convencional/todas"
            )
            if response is None or response.status_code != 200:
                return self._failure(
                    operation=operation,
                    response=response,
                    attempts=attempts,
                    error=error,
                )
            envelope = response.json()
            if not isinstance(envelope, Mapping) or int(envelope.get("estado", 0)) != 200:
                raise ValueError("AEMET returned an invalid response envelope")
            data_url = str(envelope.get("datos") or "")
            parsed_base = urlsplit(self.base_url)
            parsed_data = urlsplit(data_url)
            if (
                parsed_data.scheme.lower() != "https"
                or parsed_data.hostname != parsed_base.hostname
                or parsed_data.username
                or parsed_data.password
            ):
                raise ValueError("AEMET returned a data URL outside its trusted host")
            data_response, data_attempts, data_error = self._get(data_url)
            attempts += data_attempts
            if data_response is None or data_response.status_code != 200:
                return self._failure(
                    operation=operation,
                    response=data_response,
                    attempts=attempts,
                    error=data_error,
                )
            rows = data_response.json()
            if not isinstance(rows, list):
                raise ValueError("AEMET returned an invalid observation collection")
            candidates: list[tuple[float, datetime, Mapping[str, Any]]] = []
            for raw in rows:
                if not isinstance(raw, Mapping):
                    continue
                latitude = _number(raw.get("lat"))
                longitude = _number(raw.get("lon"))
                observed_at = _utc_naive(raw.get("fint"))
                station = str(raw.get("idema") or "").strip()
                if latitude is None or longitude is None or observed_at is None or not station:
                    continue
                if normalized.starts_at and observed_at < normalized.starts_at:
                    continue
                if normalized.ends_at and observed_at > normalized.ends_at:
                    continue
                distance = _distance_km(
                    normalized.latitude,
                    normalized.longitude,
                    latitude,
                    longitude,
                )
                if distance <= normalized.max_distance_km:
                    candidates.append((distance, observed_at, raw))
            if not candidates:
                return IntegrationResult.failed(
                    provider=self.provider_name,
                    operation=operation,
                    failure=IntegrationFailure(
                        "no_station_in_range",
                        "AEMET has no current station observation within the requested distance",
                    ),
                    attempts=attempts,
                )
            nearest_station = str(min(candidates, key=lambda row: row[0])[2].get("idema"))
            station_rows = [row for row in candidates if str(row[2].get("idema")) == nearest_station]
            distance, observed_at, raw = max(station_rows, key=lambda row: row[1])
            metrics = tuple(
                WeatherMetric(metric=name, value=value, unit=unit)
                for field, (name, unit) in _METRICS.items()
                for value in [_number(raw.get(field))]
                if value is not None
            )
            if not metrics:
                raise ValueError("AEMET station record contained no supported measurements")
            snapshot = WeatherSnapshot(
                source_reference=nearest_station[:160],
                source_name=str(raw.get("ubi"))[:240] if raw.get("ubi") else None,
                observed_at=observed_at,
                latitude=_number(raw.get("lat")),
                longitude=_number(raw.get("lon")),
                distance_km=round(distance, 3),
                metrics=metrics,
                provenance={
                    "provider": "AEMET OpenData",
                    "adapter_version": self.adapter_version,
                    "product": "observacion_convencional_todas",
                    "station_altitude_m": _number(raw.get("alt")),
                    "source_updated_at": raw.get("fint"),
                },
            )
            return IntegrationResult.succeeded(
                provider=self.provider_name,
                operation=operation,
                value=(snapshot,),
                attempts=attempts,
            )
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation=operation,
                failure=IntegrationFailure(
                    "invalid_provider_response",
                    sanitize_integration_message(exc, secret_values=(self.api_key,)),
                ),
            )

    def forecast(
        self,
        request: WeatherRequest | Mapping[str, Any],
    ) -> IntegrationResult[tuple[WeatherSnapshot, ...]]:
        """Compatibility entrypoint; Phase 15 persists current observations."""

        return self.observations(request)
