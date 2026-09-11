"""HTTP schemas for bounded place discovery and route estimates."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CoordinateIn(BaseModel):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)


class PlaceAutocompleteIn(BaseModel):
    query: str = Field(min_length=2, max_length=160)
    session_token: str = Field(pattern=r"^[A-Za-z0-9_-]{1,36}$")
    language_code: str = Field(
        default="pt", pattern=r"^[A-Za-z]{2,3}(?:-[A-Za-z]{2})?$"
    )
    region_code: str | None = Field(default=None, pattern=r"^[A-Za-z]{2}$")
    bias: CoordinateIn | None = None


class PlaceResolveIn(BaseModel):
    provider_reference: str = Field(pattern=r"^[A-Za-z0-9_-]{1,256}$")
    session_token: str = Field(pattern=r"^[A-Za-z0-9_-]{1,36}$")
    language_code: str = Field(
        default="pt", pattern=r"^[A-Za-z]{2,3}(?:-[A-Za-z]{2})?$"
    )


class RouteComputeIn(BaseModel):
    origin: CoordinateIn
    destination: CoordinateIn
    language_code: str = Field(
        default="pt", pattern=r"^[A-Za-z]{2,3}(?:-[A-Za-z]{2})?$"
    )


class ReverseGeocodeIn(BaseModel):
    coordinate: CoordinateIn
    language_code: str = Field(
        default="pt", pattern=r"^[A-Za-z]{2,3}(?:-[A-Za-z]{2})?$"
    )
    region_code: str | None = Field(default=None, pattern=r"^[A-Za-z]{2}$")


class PlaceSuggestionOut(BaseModel):
    provider_reference: str
    primary_text: str
    secondary_text: str


class PlaceAutocompleteOut(BaseModel):
    provider: str
    simulated: bool
    suggestions: list[PlaceSuggestionOut]


class ResolvedPlaceOut(BaseModel):
    provider: str
    simulated: bool
    provider_reference: str
    display_name: str
    formatted_address: str
    coordinate: CoordinateIn


class RouteEstimateOut(BaseModel):
    provider: str
    simulated: bool
    distance_meters: int
    duration_seconds: int
    encoded_polyline: str | None = None
    traffic_aware: bool


class ReverseGeocodeOut(BaseModel):
    provider: str
    simulated: bool
    provider_reference: str
    formatted_address: str
    coordinate: CoordinateIn
    granularity: str | None = None


__all__ = [
    "CoordinateIn",
    "PlaceAutocompleteIn",
    "PlaceAutocompleteOut",
    "PlaceResolveIn",
    "PlaceSuggestionOut",
    "ResolvedPlaceOut",
    "ReverseGeocodeIn",
    "ReverseGeocodeOut",
    "RouteComputeIn",
    "RouteEstimateOut",
]
