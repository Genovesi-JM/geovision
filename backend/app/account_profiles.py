"""Canonical public account profiles used by every onboarding path."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


PUBLIC_SECTORS = {"home", "agro", "environment", "construction", "industry", "infrastructure"}

# Historical web and mobile builds used a few sector names that no longer match
# the public account model. Keep accepting them at API boundaries, but always
# persist and return the current canonical identifier.
PUBLIC_SECTOR_ALIASES = {
    "agriculture": "agro",
    "livestock": "agro",
    "ambiental": "environment",
    "mining": "industry",
}


def normalize_public_sector(value: str | None) -> str:
    key = (value or "").strip().lower()
    return PUBLIC_SECTOR_ALIASES.get(key, key)


@dataclass(frozen=True)
class CustomerProfile:
    entity_type: str
    dashboard_profile: str
    default_sector: str
    allowed_sectors: tuple[str, ...]
    default_use_cases: tuple[str, ...]
    allowed_use_cases: tuple[str, ...]


CUSTOMER_PROFILES: dict[str, CustomerProfile] = {
    "home": CustomerProfile(
        "individual", "home", "home", ("home",),
        ("water", "leaks"),
        ("water", "leaks", "comfort", "air_quality", "security", "weather"),
    ),
    "farm": CustomerProfile(
        "individual", "farm", "agro", ("agro", "environment"),
        ("soil", "water", "weather"),
        ("soil", "irrigation", "water", "weather", "livestock"),
    ),
    "site": CustomerProfile(
        "individual", "site", "environment", ("environment", "infrastructure"),
        ("air_quality", "water", "leaks"),
        ("comfort", "air_quality", "water", "leaks", "weather"),
    ),
    "construction": CustomerProfile(
        "company", "construction", "construction", ("construction", "environment"),
        ("progress", "site_environment"),
        ("progress", "inspections", "site_environment", "equipment"),
    ),
    "business": CustomerProfile(
        "company", "business", "environment", ("environment", "infrastructure", "agro"),
        ("site_environment", "maintenance"),
        ("air_quality", "water", "site_environment", "maintenance", "equipment"),
    ),
    "environment": CustomerProfile(
        "company", "environment", "environment", ("environment",),
        ("air_quality", "land_change"),
        ("air_quality", "water", "weather", "land_change", "inspections"),
    ),
    "industry": CustomerProfile(
        "company", "industry", "industry", ("industry", "infrastructure"),
        ("site_environment", "maintenance"),
        ("site_environment", "maintenance", "equipment", "inventory", "inspections"),
    ),
    "device": CustomerProfile(
        "individual", "device", "environment", ("home", "environment", "agro", "infrastructure", "construction", "industry"),
        ("device_monitoring",),
        ("device_monitoring", "air_quality", "soil", "water", "weather", "equipment"),
    ),
    "enterprise": CustomerProfile(
        "company", "enterprise", "infrastructure", ("home", "agro", "environment", "construction", "industry", "infrastructure"),
        ("site_environment", "maintenance"),
        ("soil", "irrigation", "water", "weather", "livestock", "comfort", "air_quality",
         "leaks", "progress", "inspections", "site_environment", "maintenance", "equipment",
         "security", "land_change", "inventory"),
    ),
}


def normalize_account_profile(
    customer_type: str | None,
    sectors: Iterable[str] | None = None,
    sector_focus: str | None = None,
    use_cases: Iterable[str] | None = None,
) -> dict[str, object]:
    """Validate a public onboarding choice and derive its durable account profile."""
    key = (customer_type or "farm").strip().lower()
    profile = CUSTOMER_PROFILES.get(key)
    if not profile:
        raise ValueError("Invalid customer_type")

    requested_sectors = [normalize_public_sector(str(s)) for s in (sectors or []) if str(s).strip()]
    if not requested_sectors and sector_focus:
        requested_sectors = [normalize_public_sector(s) for s in sector_focus.split(",") if s.strip()]
    requested_sectors = list(dict.fromkeys(requested_sectors))
    if not requested_sectors:
        requested_sectors = [profile.default_sector]
    if any(s not in PUBLIC_SECTORS or s not in profile.allowed_sectors for s in requested_sectors):
        raise ValueError("Invalid sector for customer_type")

    requested_use_cases = list(dict.fromkeys(
        str(u).strip().lower() for u in (use_cases or []) if str(u).strip()
    ))
    if not requested_use_cases:
        requested_use_cases = list(profile.default_use_cases)
    if any(u not in profile.allowed_use_cases for u in requested_use_cases):
        raise ValueError("Invalid use_case for customer_type")

    return {
        "customer_type": key,
        "entity_type": profile.entity_type,
        "dashboard_profile": profile.dashboard_profile,
        "sectors": requested_sectors,
        "sector_focus": ",".join(requested_sectors),
        "use_cases": requested_use_cases,
    }
