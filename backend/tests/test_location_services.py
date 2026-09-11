"""Phase 37 location-provider and authenticated API tests."""

from __future__ import annotations

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.integrations.location.fake import DeterministicLocationProvider
from app.integrations.location.google_maps import GoogleMapsLocationProvider
from app.modules.assets.location_ports import GeoCoordinate
from app.routers.location import get_location_provider


def _auth_headers(client) -> dict[str, str]:
    response = client.post(
        "/auth/login",
        json={"email": "teste@clientes.com", "password": "123456"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_settings_fail_closed_and_redact_google_maps_server_key(monkeypatch):
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    with pytest.raises(ValidationError, match="GOOGLE_MAPS_SERVER_API_KEY"):
        Settings(_env_file=None, location_provider="google_maps")

    configured = Settings(
        _env_file=None,
        location_provider="google_maps",
        google_maps_server_api_key="server-key-that-must-not-leak",
    )
    assert configured.model_dump()["google_maps_server_api_key"] == "[REDACTED]"
    assert configured.safe_summary()["configured"]["google_maps_location"] is True


def test_google_adapter_uses_header_key_field_masks_and_normalizes_results():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["X-Goog-Api-Key"] == "secret-server-key"
        assert "secret-server-key" not in str(request.url)
        if request.url.path.endswith("places:autocomplete"):
            return httpx.Response(
                200,
                json={
                    "suggestions": [
                        {
                            "placePrediction": {
                                "placeId": "ChIJ-Luanda",
                                "structuredFormat": {
                                    "mainText": {"text": "Luanda"},
                                    "secondaryText": {"text": "Angola"},
                                },
                            }
                        }
                    ]
                },
            )
        if request.url.path.endswith("/places/ChIJ-Luanda"):
            return httpx.Response(
                200,
                json={
                    "id": "ChIJ-Luanda",
                    "displayName": {"text": "Luanda"},
                    "formattedAddress": "Luanda, Angola",
                    "location": {"latitude": -8.838333, "longitude": 13.234444},
                },
            )
        return httpx.Response(
            200,
            json={
                "routes": [
                    {
                        "distanceMeters": 13200,
                        "duration": "1250s",
                        "polyline": {"encodedPolyline": "safe-polyline"},
                    }
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = GoogleMapsLocationProvider(
        api_key="secret-server-key",
        client=client,
    )
    bias = GeoCoordinate(latitude=-8.8, longitude=13.2)
    suggestions = provider.autocomplete(
        query="Lua",
        session_token="session-1",
        language_code="pt",
        region_code="AO",
        bias=bias,
    )
    assert suggestions.ok
    assert suggestions.value[0].provider_reference == "ChIJ-Luanda"

    place = provider.resolve_place(
        provider_reference="ChIJ-Luanda",
        session_token="session-1",
        language_code="pt",
    )
    assert place.ok
    assert place.value.coordinate == GeoCoordinate(-8.838333, 13.234444)

    route = provider.compute_route(
        origin=bias,
        destination=place.value.coordinate,
        language_code="pt",
    )
    assert route.ok
    assert route.value.distance_meters == 13200
    assert route.value.duration_seconds == 1250
    assert len(requests) == 3
    assert "routes.distanceMeters" in requests[-1].headers["X-Goog-FieldMask"]
    client.close()


def test_google_adapter_rejects_unsafe_place_reference_without_http():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = GoogleMapsLocationProvider(api_key="server-key", client=client)
    result = provider.resolve_place(
        provider_reference="../../routes.googleapis.com",
        session_token="session-1",
        language_code="pt",
    )
    assert not result.ok
    assert result.failure.code == "invalid_place_reference"
    assert calls == 0
    client.close()


def test_authenticated_location_journey_uses_one_autocomplete_session(client):
    client.app.dependency_overrides[get_location_provider] = (
        lambda: DeterministicLocationProvider()
    )
    try:
        assert client.get("/location/capabilities").status_code == 401
        headers = _auth_headers(client)
        session = "550e8400-e29b-41d4-a716-446655440000"
        autocomplete = client.post(
            "/location/places:autocomplete",
            headers=headers,
            json={
                "query": "Luanda",
                "session_token": session,
                "language_code": "pt",
                "region_code": "AO",
            },
        )
        assert autocomplete.status_code == 200, autocomplete.text
        suggestion = autocomplete.json()["suggestions"][0]
        assert suggestion["provider_reference"] == "fake-luanda"
        assert autocomplete.json()["simulated"] is True

        resolved = client.post(
            "/location/places:resolve",
            headers=headers,
            json={
                "provider_reference": suggestion["provider_reference"],
                "session_token": session,
                "language_code": "pt",
            },
        )
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["coordinate"]["latitude"] == -8.838333

        route = client.post(
            "/location/routes:compute",
            headers=headers,
            json={
                "origin": {"latitude": -8.9, "longitude": 13.1},
                "destination": resolved.json()["coordinate"],
                "language_code": "pt",
            },
        )
        assert route.status_code == 200, route.text
        assert route.json()["distance_meters"] > 0
        assert route.json()["simulated"] is True
    finally:
        client.app.dependency_overrides.pop(get_location_provider, None)


def test_location_request_validation_rejects_bad_tokens_and_coordinates(client):
    headers = _auth_headers(client)
    response = client.post(
        "/location/routes:compute",
        headers=headers,
        json={
            "origin": {"latitude": 91, "longitude": 13},
            "destination": {"latitude": 40, "longitude": -3},
        },
    )
    assert response.status_code == 422

    response = client.post(
        "/location/places:autocomplete",
        headers=headers,
        json={"query": "Luanda", "session_token": "contains spaces"},
    )
    assert response.status_code == 422
