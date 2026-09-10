"""Canonical customer-facing sector taxonomy and compatibility mappings.

Public sectors describe the market/customer context.  Technical sector packages
remain reusable capability bundles, so a public sector may intentionally reuse
an existing package without collapsing its customer identity.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import re
import unicodedata


@dataclass(frozen=True, slots=True)
class PublicSectorDefinition:
    id: str
    label_pt: str
    slug_pt: str
    asset_sector: str
    capability_sector: str
    maturity: str
    aliases: tuple[str, ...] = ()


PUBLIC_SECTOR_DEFINITIONS: tuple[PublicSectorDefinition, ...] = (
    PublicSectorDefinition(
        id="agriculture",
        label_pt="Agricultura & Pecuária",
        slug_pt="agricultura-pecuaria",
        asset_sector="AGRICULTURE",
        capability_sector="agriculture",
        maturity="available",
        aliases=(
            "agro",
            "agropecuaria",
            "agricultura",
            "agricultura_e_pecuaria",
            "agricultura_pecuaria",
            "agriculture_livestock",
            "livestock",
        ),
    ),
    PublicSectorDefinition(
        id="construction_infrastructure",
        label_pt="Construção & Infraestruturas",
        slug_pt="construcao-infraestruturas",
        asset_sector="INFRASTRUCTURE",
        capability_sector="infrastructure",
        maturity="custom_project",
        aliases=(
            "construction",
            "construction_and_infrastructure",
            "construcao_e_infraestruturas",
            "construcao_infraestrutura",
            "construcao_infraestruturas",
            "infrastructure",
            "infrastructures",
        ),
    ),
    PublicSectorDefinition(
        id="environment",
        label_pt="Ambiente",
        slug_pt="ambiente",
        asset_sector="ENVIRONMENTAL",
        capability_sector="environmental",
        maturity="custom_project",
        aliases=("ambiente", "ambiental", "environmental"),
    ),
    PublicSectorDefinition(
        id="mining",
        label_pt="Mineração",
        slug_pt="mineracao",
        asset_sector="MINING",
        capability_sector="mining",
        maturity="specialized",
        aliases=("mine", "mines", "mineracao", "quarry"),
    ),
    PublicSectorDefinition(
        id="industry_energy_utilities",
        label_pt="Indústria, Energia & Utilities",
        slug_pt="industria-energia-utilities",
        asset_sector="INDUSTRY_ENERGY_UTILITIES",
        capability_sector="industry_energy_utilities",
        maturity="expansion",
        aliases=(
            "energy",
            "energia",
            "industrial",
            "industria",
            "industria_e_energia_utilities",
            "industria_energia_e_utilities",
            "industria_energia_utilities",
            "industry",
            "industry_energy",
            "solar",
            "utilities",
        ),
    ),
    PublicSectorDefinition(
        id="ports_logistics",
        label_pt="Portos & Logística",
        slug_pt="portos-logistica",
        asset_sector="PORTS_LOGISTICS",
        capability_sector="ports_logistics",
        maturity="expansion",
        aliases=(
            "logistics",
            "logistica",
            "port",
            "ports",
            "ports_and_logistics",
            "portos",
            "portos_e_logistica",
            "portos_logistica",
            "ports_industrial",
        ),
    ),
)

PUBLIC_SECTOR_IDS = tuple(item.id for item in PUBLIC_SECTOR_DEFINITIONS)
PUBLIC_SECTORS = frozenset(PUBLIC_SECTOR_IDS)
CAPABILITY_MODULE_IDS = tuple(
    item.capability_sector for item in PUBLIC_SECTOR_DEFINITIONS
)
PUBLIC_SECTORS_BY_ID = {item.id: item for item in PUBLIC_SECTOR_DEFINITIONS}
PUBLIC_SECTORS_BY_ASSET_SECTOR = {
    item.asset_sector: item for item in PUBLIC_SECTOR_DEFINITIONS
}


def _key(value: str | None) -> str:
    ascii_value = "".join(
        character
        for character in unicodedata.normalize("NFKD", str(value or ""))
        if not unicodedata.combining(character)
    )
    return re.sub(r"[^a-z0-9]+", "_", ascii_value.strip().lower()).strip("_")


def _comma_phrase_key(value: str) -> str:
    ascii_value = "".join(
        character
        for character in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(character)
    )
    compact = re.sub(r"\s*,\s*", ",", ascii_value.strip().lower())
    return re.sub(r"\s+", " ", compact)


PUBLIC_SECTOR_ALIASES = {
    alias: definition.id
    for definition in PUBLIC_SECTOR_DEFINITIONS
    for alias in (definition.id, *definition.aliases)
}

_COMMA_BEARING_PUBLIC_LABELS = {
    _comma_phrase_key(label): "industry_energy_utilities"
    for label in (
        "Indústria, Energia & Utilities",
        "Indústria, Energia e Utilities",
        "Industry, Energy & Utilities",
    )
}
_MAX_COMMA_BEARING_LABEL_PARTS = max(
    label.count(",") + 1 for label in _COMMA_BEARING_PUBLIC_LABELS
)


def normalize_public_sector(value: str | None) -> str:
    """Return a canonical public identifier while leaving unknown values visible."""

    raw = str(value or "").strip()
    key = _key(raw)
    return PUBLIC_SECTOR_ALIASES.get(key, key or raw)


def normalize_sector_focus(value: str | None) -> str:
    """Normalize and de-duplicate a comma-separated public sector selection."""

    return ",".join(normalize_public_sector_values([value] if value else []))


def _split_public_sector_csv(value: str) -> list[str]:
    """Split selections without breaking labels that contain commas."""

    parts = value.split(",")
    output: list[str] = []
    index = 0
    while index < len(parts):
        match: tuple[str, int] | None = None
        furthest_end = min(len(parts), index + _MAX_COMMA_BEARING_LABEL_PARTS)
        for end in range(furthest_end, index + 1, -1):
            candidate = ",".join(parts[index:end]).strip()
            normalized = _COMMA_BEARING_PUBLIC_LABELS.get(_comma_phrase_key(candidate))
            if normalized is not None:
                match = (normalized, end)
                break
        if match is not None:
            normalized, index = match
            output.append(normalized)
            continue
        normalized = normalize_public_sector(parts[index])
        if normalized:
            output.append(normalized)
        index += 1
    return output


def normalize_public_sector_values(
    values: Iterable[object] | object | None,
) -> list[str]:
    """Normalize scalar/list inputs without splitting the comma in a known label."""

    if values is None:
        return []
    source = (
        values
        if isinstance(values, Iterable) and not isinstance(values, (str, bytes))
        else [values]
    )
    output: list[str] = []
    seen: set[str] = set()
    for value in source:
        if value is None:
            continue
        raw = str(value).strip()
        if not raw:
            continue
        candidates = _split_public_sector_csv(raw)
        for item in candidates:
            if item in seen:
                continue
            seen.add(item)
            output.append(item)
    return output


def normalize_capability_modules(
    values: Iterable[object] | object | None,
) -> list[str]:
    """Canonicalize sector-module aliases while preserving unrelated modules."""

    if values is None:
        return []
    source = (
        values
        if isinstance(values, Iterable) and not isinstance(values, (str, bytes))
        else [values]
    )
    output: list[str] = []
    seen: set[str] = set()
    for value in source:
        if value is None:
            continue
        raw = str(value).strip()
        if not raw:
            continue
        public_id = PUBLIC_SECTOR_ALIASES.get(_key(raw))
        normalized = (
            PUBLIC_SECTORS_BY_ID[public_id].capability_sector
            if public_id is not None
            else raw
        )
        if normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output


def public_sector_values(values: Iterable[object] | object | None) -> list[str]:
    """Project legacy input onto the supported public taxonomy for read APIs."""

    return [
        value
        for value in normalize_public_sector_values(values)
        if value in PUBLIC_SECTORS
    ]


def public_sector_focus(value: str | None) -> str:
    """Return only supported public sectors from a persisted focus string."""

    return ",".join(public_sector_values([value] if value else []))


def public_sector_definition(value: str) -> PublicSectorDefinition | None:
    return PUBLIC_SECTORS_BY_ID.get(normalize_public_sector(value))


def asset_sector_for_public(value: str) -> str | None:
    definition = public_sector_definition(value)
    return definition.asset_sector if definition else None


def capability_sector_for_public(value: str) -> str | None:
    definition = public_sector_definition(value)
    return definition.capability_sector if definition else None


def public_sector_for_asset(value: str | None) -> str:
    normalized = (
        re.sub(r"[^A-Za-z0-9]+", "_", str(value or "").strip()).strip("_").upper()
    )
    legacy = {
        "AGRO": "AGRICULTURE",
        "LIVESTOCK": "AGRICULTURE",
        "CONSTRUCTION": "INFRASTRUCTURE",
        "CONSTRUCTION_INFRASTRUCTURE": "INFRASTRUCTURE",
        "ENVIRONMENT": "ENVIRONMENTAL",
        "AMBIENTAL": "ENVIRONMENTAL",
        "INDUSTRY": "INDUSTRY_ENERGY_UTILITIES",
        "INDUSTRIAL": "INDUSTRY_ENERGY_UTILITIES",
        "ENERGY": "INDUSTRY_ENERGY_UTILITIES",
        "UTILITIES": "INDUSTRY_ENERGY_UTILITIES",
        "PORT": "PORTS_LOGISTICS",
        "PORTS": "PORTS_LOGISTICS",
        "LOGISTICS": "PORTS_LOGISTICS",
        "PORTS_INDUSTRIAL": "PORTS_LOGISTICS",
    }
    normalized = legacy.get(normalized, normalized)
    definition = PUBLIC_SECTORS_BY_ASSET_SECTOR.get(normalized)
    return definition.id if definition else normalize_public_sector(value)


__all__ = [
    "CAPABILITY_MODULE_IDS",
    "PUBLIC_SECTOR_ALIASES",
    "PUBLIC_SECTOR_DEFINITIONS",
    "PUBLIC_SECTOR_IDS",
    "PUBLIC_SECTORS",
    "PUBLIC_SECTORS_BY_ASSET_SECTOR",
    "PUBLIC_SECTORS_BY_ID",
    "PublicSectorDefinition",
    "asset_sector_for_public",
    "capability_sector_for_public",
    "normalize_public_sector",
    "normalize_public_sector_values",
    "normalize_capability_modules",
    "normalize_sector_focus",
    "public_sector_focus",
    "public_sector_definition",
    "public_sector_for_asset",
    "public_sector_values",
]
