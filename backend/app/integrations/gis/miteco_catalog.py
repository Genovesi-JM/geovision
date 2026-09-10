"""Reviewed MITECO GIS collections exposed to GeoVision.

Collection identifiers are provider-owned references. Adding a collection is a
reviewed code change so arbitrary public GeoServer layers cannot be queried
through the application merely by supplying their name.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping
from urllib.parse import quote


MITECO_OGC_FEATURES_BASE_URL = (
    "https://gis.miteco.gob.es/geoserver/ogc/features/v1"
)
MITECO_REUSE_NOTICE_URL = "https://www.datosabiertos.miteco.gob.es/es/aviso-legal.html"
MITECO_ATTRIBUTION = (
    "Origen de los datos: Ministerio para la Transición ecológica y el Reto "
    "Demográfico"
)
MITECO_SPAIN_CRS84_BBOX = (-18.5, 27.0, 5.0, 44.5)


@dataclass(frozen=True, slots=True)
class MitecoCollection:
    """Immutable reviewed metadata for one official provider collection."""

    key: str
    collection_id: str
    title: str
    description: str
    metadata_url: str
    license_id: str
    license_url: str
    attribution: str = MITECO_ATTRIBUTION
    geographic_scope: str = "Spain"
    extent: tuple[float, float, float, float] = MITECO_SPAIN_CRS84_BBOX

    @property
    def collection_url(self) -> str:
        encoded_id = quote(self.collection_id, safe="")
        return f"{MITECO_OGC_FEATURES_BASE_URL}/collections/{encoded_id}"


_COLLECTIONS = {
    "biodiversity_priority_zones": MitecoCollection(
        key="biodiversity_priority_zones",
        collection_id="costas:poem_uso_prio_biodiv_zupbd",
        title="Zonas de uso prioritario para la protección de la biodiversidad",
        description=(
            "Official biodiversity-protection context published through the "
            "MITECO IDE; it is not a diagnosis or a GeoVision measurement."
        ),
        metadata_url=(
            "https://gis.miteco.gob.es/geoserver/ogc/features/v1/collections/"
            "costas%3Apoem_uso_prio_biodiv_zupbd"
        ),
        license_id="MITECO-GENERAL-REUSE-CONDITIONS",
        license_url=MITECO_REUSE_NOTICE_URL,
    ),
}

MITECO_COLLECTIONS: Mapping[str, MitecoCollection] = MappingProxyType(_COLLECTIONS)


def get_miteco_collection(key: str) -> MitecoCollection | None:
    """Resolve a public application key without accepting provider URLs."""

    normalized = key.strip().lower().replace("-", "_")
    return MITECO_COLLECTIONS.get(normalized)


__all__ = [
    "MITECO_ATTRIBUTION",
    "MITECO_COLLECTIONS",
    "MITECO_OGC_FEATURES_BASE_URL",
    "MITECO_REUSE_NOTICE_URL",
    "MITECO_SPAIN_CRS84_BBOX",
    "MitecoCollection",
    "get_miteco_collection",
]
