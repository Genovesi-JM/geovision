"""Cross-sector asset identifiers and portable spatial validation."""

from __future__ import annotations

import json
import math
import re
from enum import Enum
from typing import Any, Iterable, Mapping


class AssetSector(str, Enum):
    AGRICULTURE = "AGRICULTURE"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    ENVIRONMENTAL = "ENVIRONMENTAL"
    MINING = "MINING"
    PORTS_INDUSTRIAL = "PORTS_INDUSTRIAL"


class AssetStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


# Stable common identifiers. The database deliberately does not constrain this
# registry so later sector modules can add identifiers without a table rewrite.
ASSET_TYPE_REGISTRY = frozenset(
    {
        "FARM",
        "FIELD",
        "SITE",
        "FACILITY",
        "BUILDING",
        "ROAD",
        "BRIDGE",
        "RAILWAY",
        "QUARRY",
        "MINE",
        "STOCKPILE",
        "PORT",
        "TERMINAL",
        "QUAY",
        "BERTH",
        "CRANE",
        "GANTRY",
        "LOADING_AREA",
        "INSPECTION_ZONE",
        "WAREHOUSE",
        "ROOF",
        "TANK",
        "PIPELINE",
        "SOLAR_ARRAY",
        "IOT_DEVICE",
        "DRONE",
        "EQUIPMENT",
        "STRUCTURE",
        "ENVIRONMENTAL_SITE",
    }
)


_SECTOR_ALIASES = {
    "AGRO": AssetSector.AGRICULTURE.value,
    "AGRICULTURE": AssetSector.AGRICULTURE.value,
    "LIVESTOCK": AssetSector.AGRICULTURE.value,
    "CONSTRUCTION": AssetSector.INFRASTRUCTURE.value,
    "INFRASTRUCTURE": AssetSector.INFRASTRUCTURE.value,
    "ENVIRONMENT": AssetSector.ENVIRONMENTAL.value,
    "ENVIRONMENTAL": AssetSector.ENVIRONMENTAL.value,
    "AMBIENTAL": AssetSector.ENVIRONMENTAL.value,
    "MINING": AssetSector.MINING.value,
    "INDUSTRY": AssetSector.PORTS_INDUSTRIAL.value,
    "INDUSTRIAL": AssetSector.PORTS_INDUSTRIAL.value,
    "PORTS": AssetSector.PORTS_INDUSTRIAL.value,
    "PORTS_INDUSTRIAL": AssetSector.PORTS_INDUSTRIAL.value,
}

_TYPE_ALIASES = {
    "AGRICULTURAL_FIELD": "FIELD",
    "CONSTRUCTION_SITE": "SITE",
    "DEVICE": "IOT_DEVICE",
    "SENSOR": "IOT_DEVICE",
}

_IDENTIFIER = re.compile(r"^[A-Z][A-Z0-9_]{1,79}$")
SUPPORTED_GEOMETRY_TYPES = frozenset({"Point", "Polygon", "MultiPolygon"})


class AssetValidationError(ValueError):
    """Raised when an asset identifier, hierarchy, or geometry is invalid."""


def normalize_identifier(value: str, *, field_name: str, max_length: int = 80) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "").strip()).strip("_").upper()
    if not normalized or len(normalized) > max_length or not _IDENTIFIER.fullmatch(normalized):
        raise AssetValidationError(
            f"{field_name} must be a stable uppercase identifier using letters, digits, and underscores"
        )
    return normalized


def normalize_sector(value: str) -> str:
    normalized = normalize_identifier(value, field_name="sector", max_length=50)
    return _SECTOR_ALIASES.get(normalized, normalized)


def normalize_asset_type(value: str) -> str:
    normalized = normalize_identifier(value, field_name="asset_type")
    return _TYPE_ALIASES.get(normalized, normalized)


def _position(value: Any) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise AssetValidationError("GeoJSON positions must contain longitude and latitude")
    if isinstance(value[0], bool) or isinstance(value[1], bool):
        raise AssetValidationError("GeoJSON coordinates must be numbers")
    try:
        longitude = float(value[0])
        latitude = float(value[1])
    except (TypeError, ValueError) as exc:
        raise AssetValidationError("GeoJSON coordinates must be numbers") from exc
    if not math.isfinite(longitude) or not math.isfinite(latitude):
        raise AssetValidationError("GeoJSON coordinates must be finite")
    if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
        raise AssetValidationError("GeoJSON coordinates are outside EPSG:4326 bounds")
    return [longitude, latitude]


def _ring(value: Any) -> list[list[float]]:
    if not isinstance(value, (list, tuple)) or len(value) < 4:
        raise AssetValidationError("Polygon rings require at least four positions")
    result = [_position(position) for position in value]
    if result[0] != result[-1]:
        raise AssetValidationError("Polygon rings must be closed")
    return result


def _polygon(value: Any) -> list[list[list[float]]]:
    if not isinstance(value, (list, tuple)) or not value:
        raise AssetValidationError("Polygon coordinates require an exterior ring")
    return [_ring(ring) for ring in value]


def normalize_geometry(value: Mapping[str, Any] | str | None) -> dict[str, Any] | None:
    """Validate and canonicalize one EPSG:4326 GeoJSON geometry."""

    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError) as exc:
            raise AssetValidationError("geometry must be valid GeoJSON") from exc
    if not isinstance(value, Mapping):
        raise AssetValidationError("geometry must be a GeoJSON object")
    geometry_type = value.get("type")
    if geometry_type not in SUPPORTED_GEOMETRY_TYPES:
        raise AssetValidationError(
            "geometry type must be Point, Polygon, or MultiPolygon"
        )
    coordinates = value.get("coordinates")
    if geometry_type == "Point":
        normalized_coordinates: Any = _position(coordinates)
    elif geometry_type == "Polygon":
        normalized_coordinates = _polygon(coordinates)
    else:
        if not isinstance(coordinates, (list, tuple)) or not coordinates:
            raise AssetValidationError("MultiPolygon coordinates require at least one polygon")
        normalized_coordinates = [_polygon(polygon) for polygon in coordinates]
    return {"type": geometry_type, "coordinates": normalized_coordinates}


def _positions(geometry: Mapping[str, Any]) -> Iterable[list[float]]:
    geometry_type = geometry["type"]
    coordinates = geometry["coordinates"]
    if geometry_type == "Point":
        yield coordinates
    elif geometry_type == "Polygon":
        for ring in coordinates:
            yield from ring
    else:
        for polygon in coordinates:
            for ring in polygon:
                yield from ring


def geometry_bounds(geometry: Mapping[str, Any] | None) -> tuple[float, float, float, float] | None:
    if geometry is None:
        return None
    positions = list(_positions(geometry))
    longitudes = [position[0] for position in positions]
    latitudes = [position[1] for position in positions]
    return min(longitudes), min(latitudes), max(longitudes), max(latitudes)


def geometry_display_center(geometry: Mapping[str, Any] | None) -> tuple[float, float] | None:
    """Return a stable map center (latitude, longitude), not an analytic centroid."""

    bounds = geometry_bounds(geometry)
    if bounds is None:
        return None
    min_x, min_y, max_x, max_y = bounds
    return (min_y + max_y) / 2, (min_x + max_x) / 2


def point_geometry(latitude: float | None, longitude: float | None) -> dict[str, Any] | None:
    if latitude is None or longitude is None:
        return None
    return normalize_geometry({"type": "Point", "coordinates": [longitude, latitude]})


__all__ = [
    "ASSET_TYPE_REGISTRY",
    "SUPPORTED_GEOMETRY_TYPES",
    "AssetSector",
    "AssetStatus",
    "AssetValidationError",
    "geometry_bounds",
    "geometry_display_center",
    "normalize_asset_type",
    "normalize_geometry",
    "normalize_sector",
    "point_geometry",
]
