"""Google Maps Platform Places (New) and Routes adapters."""

from __future__ import annotations

import re
from typing import Any

import httpx

from app.core.integration import IntegrationFailure, IntegrationResult
from app.modules.assets.location_ports import (
    GeoCoordinate,
    PlaceSuggestion,
    ResolvedPlace,
    ReverseGeocodedAddress,
    RouteEstimate,
)


_PLACE_ID = re.compile(r"^[A-Za-z0-9_-]{1,256}$")


class GoogleMapsLocationProvider:
    provider_name = "google_maps"
    configured = True
    places_base_url = "https://places.googleapis.com/v1"
    routes_url = "https://routes.googleapis.com/directions/v2:computeRoutes"
    geocode_url = "https://geocode.googleapis.com/v4/geocode/location"

    def __init__(
        self,
        *,
        api_key: str,
        connect_timeout_seconds: float = 5.0,
        read_timeout_seconds: float = 20.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Google Maps API key is required")
        self._api_key = api_key
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(
                connect=connect_timeout_seconds,
                read=read_timeout_seconds,
                write=read_timeout_seconds,
                pool=connect_timeout_seconds,
            )
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _headers(self, field_mask: str) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": field_mask,
        }

    def autocomplete(
        self,
        *,
        query: str,
        session_token: str,
        language_code: str,
        region_code: str | None = None,
        bias: GeoCoordinate | None = None,
    ) -> IntegrationResult[tuple[PlaceSuggestion, ...]]:
        operation = "autocomplete"
        payload: dict[str, Any] = {
            "input": query,
            "sessionToken": session_token,
            "languageCode": language_code,
            "includeQueryPredictions": False,
        }
        if region_code:
            payload["regionCode"] = region_code
        if bias:
            payload["locationBias"] = {
                "circle": {
                    "center": {
                        "latitude": bias.latitude,
                        "longitude": bias.longitude,
                    },
                    "radius": 50_000.0,
                }
            }
        try:
            response = self._client.post(
                f"{self.places_base_url}/places:autocomplete",
                headers=self._headers(
                    "suggestions.placePrediction.placeId,"
                    "suggestions.placePrediction.structuredFormat"
                ),
                json=payload,
            )
            response.raise_for_status()
            suggestions: list[PlaceSuggestion] = []
            for row in response.json().get("suggestions", []):
                prediction = row.get("placePrediction") or {}
                structured = prediction.get("structuredFormat") or {}
                primary = (structured.get("mainText") or {}).get("text", "")
                secondary = (structured.get("secondaryText") or {}).get("text", "")
                place_id = prediction.get("placeId", "")
                if _PLACE_ID.fullmatch(str(place_id)) and str(primary).strip():
                    suggestions.append(
                        PlaceSuggestion(
                            provider_reference=str(place_id),
                            primary_text=str(primary).strip(),
                            secondary_text=str(secondary).strip(),
                        )
                    )
            return IntegrationResult.succeeded(
                provider=self.provider_name,
                operation=operation,
                value=tuple(suggestions[:8]),
            )
        except httpx.TimeoutException:
            return self._failed(operation, "provider_timeout", retryable=True)
        except httpx.HTTPStatusError as exc:
            return self._failed(
                operation,
                "provider_rate_limited"
                if exc.response.status_code == 429
                else "provider_http_error",
                retryable=exc.response.status_code == 429
                or exc.response.status_code >= 500,
            )
        except (httpx.HTTPError, TypeError, ValueError, AttributeError):
            return self._failed(operation, "provider_response_invalid")

    def resolve_place(
        self,
        *,
        provider_reference: str,
        session_token: str,
        language_code: str,
    ) -> IntegrationResult[ResolvedPlace]:
        operation = "resolve_place"
        if not _PLACE_ID.fullmatch(provider_reference):
            return self._failed(operation, "invalid_place_reference")
        try:
            response = self._client.get(
                f"{self.places_base_url}/places/{provider_reference}",
                headers=self._headers("id,displayName,formattedAddress,location"),
                params={
                    "languageCode": language_code,
                    "sessionToken": session_token,
                },
            )
            response.raise_for_status()
            payload = response.json()
            location = payload["location"]
            resolved = ResolvedPlace(
                provider_reference=str(payload.get("id") or provider_reference),
                display_name=str(
                    (payload.get("displayName") or {}).get("text") or ""
                ).strip(),
                formatted_address=str(payload.get("formattedAddress") or "").strip(),
                coordinate=GeoCoordinate(
                    latitude=float(location["latitude"]),
                    longitude=float(location["longitude"]),
                ),
            )
            if not resolved.display_name:
                raise ValueError("missing display name")
            return IntegrationResult.succeeded(
                provider=self.provider_name,
                operation=operation,
                value=resolved,
            )
        except httpx.TimeoutException:
            return self._failed(operation, "provider_timeout", retryable=True)
        except httpx.HTTPStatusError as exc:
            return self._failed(
                operation,
                "place_not_found"
                if exc.response.status_code == 404
                else "provider_http_error",
                retryable=exc.response.status_code >= 500,
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError, AttributeError):
            return self._failed(operation, "provider_response_invalid")

    def compute_route(
        self,
        *,
        origin: GeoCoordinate,
        destination: GeoCoordinate,
        language_code: str,
    ) -> IntegrationResult[RouteEstimate]:
        operation = "compute_route"
        payload = {
            "origin": {"location": {"latLng": _point(origin)}},
            "destination": {"location": {"latLng": _point(destination)}},
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_UNAWARE",
            "computeAlternativeRoutes": False,
            "languageCode": language_code,
            "units": "METRIC",
        }
        try:
            response = self._client.post(
                self.routes_url,
                headers=self._headers(
                    "routes.duration,routes.distanceMeters,"
                    "routes.polyline.encodedPolyline"
                ),
                json=payload,
            )
            response.raise_for_status()
            route = response.json()["routes"][0]
            duration = str(route["duration"])
            if not duration.endswith("s"):
                raise ValueError("unexpected duration")
            estimate = RouteEstimate(
                distance_meters=int(route["distanceMeters"]),
                duration_seconds=round(float(duration[:-1])),
                encoded_polyline=(route.get("polyline") or {}).get("encodedPolyline"),
                traffic_aware=False,
            )
            return IntegrationResult.succeeded(
                provider=self.provider_name,
                operation=operation,
                value=estimate,
            )
        except httpx.TimeoutException:
            return self._failed(operation, "provider_timeout", retryable=True)
        except httpx.HTTPStatusError as exc:
            return self._failed(
                operation,
                "provider_rate_limited"
                if exc.response.status_code == 429
                else "provider_http_error",
                retryable=exc.response.status_code == 429
                or exc.response.status_code >= 500,
            )
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
            return self._failed(operation, "provider_response_invalid")

    def reverse_geocode(
        self,
        *,
        coordinate: GeoCoordinate,
        language_code: str,
        region_code: str | None = None,
    ) -> IntegrationResult[ReverseGeocodedAddress]:
        operation = "reverse_geocode"
        params: dict[str, str | float] = {
            "location.latitude": coordinate.latitude,
            "location.longitude": coordinate.longitude,
            "languageCode": language_code,
        }
        if region_code:
            params["regionCode"] = region_code
        try:
            response = self._client.get(
                self.geocode_url,
                headers=self._headers(
                    "results.placeId,results.formattedAddress,"
                    "results.location,results.granularity"
                ),
                params=params,
            )
            response.raise_for_status()
            row = response.json()["results"][0]
            place_id = str(row["placeId"])
            address = str(row["formattedAddress"]).strip()
            location = row.get("location") or {}
            if not _PLACE_ID.fullmatch(place_id) or not address:
                raise ValueError("invalid geocode result")
            return IntegrationResult.succeeded(
                provider=self.provider_name,
                operation=operation,
                value=ReverseGeocodedAddress(
                    provider_reference=place_id,
                    formatted_address=address,
                    coordinate=GeoCoordinate(
                        latitude=float(location.get("latitude", coordinate.latitude)),
                        longitude=float(
                            location.get("longitude", coordinate.longitude)
                        ),
                    ),
                    granularity=str(row.get("granularity") or "").strip() or None,
                ),
            )
        except httpx.TimeoutException:
            return self._failed(operation, "provider_timeout", retryable=True)
        except httpx.HTTPStatusError as exc:
            return self._failed(
                operation,
                "provider_rate_limited"
                if exc.response.status_code == 429
                else "provider_http_error",
                retryable=exc.response.status_code == 429
                or exc.response.status_code >= 500,
            )
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
            return self._failed(operation, "provider_response_invalid")

    def _failed(self, operation: str, code: str, *, retryable: bool = False):
        return IntegrationResult.failed(
            provider=self.provider_name,
            operation=operation,
            failure=IntegrationFailure(
                code=code,
                message="Google Maps Platform request was not completed",
                retryable=retryable,
            ),
        )


def _point(value: GeoCoordinate) -> dict[str, float]:
    return {"latitude": value.latitude, "longitude": value.longitude}


__all__ = ["GoogleMapsLocationProvider"]
