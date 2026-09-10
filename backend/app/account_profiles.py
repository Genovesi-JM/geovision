"""Canonical public account profiles used by every onboarding path."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.sector_taxonomy import (
    PUBLIC_SECTORS,
    normalize_public_sector_values,
)


@dataclass(frozen=True)
class CustomerProfile:
    entity_type: str
    dashboard_profile: str
    default_sector: str
    allowed_sectors: tuple[str, ...]
    default_use_cases: tuple[str, ...]
    allowed_use_cases: tuple[str, ...]


CUSTOMER_PROFILES: dict[str, CustomerProfile] = {
    "farm": CustomerProfile(
        "individual",
        "farm",
        "agriculture",
        ("agriculture", "environment"),
        ("soil", "water", "weather"),
        ("soil", "irrigation", "water", "weather", "livestock"),
    ),
    "site": CustomerProfile(
        "individual",
        "site",
        "environment",
        ("environment", "construction_infrastructure"),
        ("air_quality", "water", "leaks"),
        ("comfort", "air_quality", "water", "leaks", "weather"),
    ),
    "construction": CustomerProfile(
        "company",
        "construction",
        "construction_infrastructure",
        ("construction_infrastructure", "environment"),
        ("progress", "site_environment"),
        ("progress", "inspections", "site_environment", "equipment"),
    ),
    "business": CustomerProfile(
        "company",
        "business",
        "environment",
        (
            "agriculture",
            "construction_infrastructure",
            "environment",
            "mining",
            "industry_energy_utilities",
            "ports_logistics",
        ),
        ("site_environment", "maintenance"),
        ("air_quality", "water", "site_environment", "maintenance", "equipment"),
    ),
    "environment": CustomerProfile(
        "company",
        "environment",
        "environment",
        ("environment",),
        ("air_quality", "land_change"),
        ("air_quality", "water", "weather", "land_change", "inspections"),
    ),
    "industry": CustomerProfile(
        "company",
        "industry",
        "industry_energy_utilities",
        (
            "industry_energy_utilities",
            "mining",
            "ports_logistics",
        ),
        ("site_environment", "maintenance"),
        ("site_environment", "maintenance", "equipment", "inventory", "inspections"),
    ),
    "mining": CustomerProfile(
        "company",
        "mining",
        "mining",
        ("mining", "environment"),
        ("inventory", "inspections"),
        ("site_environment", "maintenance", "equipment", "inventory", "inspections"),
    ),
    "ports_logistics": CustomerProfile(
        "company",
        "ports_logistics",
        "ports_logistics",
        (
            "ports_logistics",
            "construction_infrastructure",
            "environment",
        ),
        ("inventory", "equipment"),
        ("site_environment", "maintenance", "equipment", "inventory", "inspections"),
    ),
    "device": CustomerProfile(
        "individual",
        "device",
        "environment",
        (
            "agriculture",
            "construction_infrastructure",
            "environment",
            "mining",
            "industry_energy_utilities",
            "ports_logistics",
        ),
        ("device_monitoring",),
        ("device_monitoring", "air_quality", "soil", "water", "weather", "equipment"),
    ),
    "enterprise": CustomerProfile(
        "company",
        "enterprise",
        "construction_infrastructure",
        (
            "agriculture",
            "construction_infrastructure",
            "environment",
            "mining",
            "industry_energy_utilities",
            "ports_logistics",
        ),
        ("site_environment", "maintenance"),
        (
            "soil",
            "irrigation",
            "water",
            "weather",
            "livestock",
            "comfort",
            "air_quality",
            "leaks",
            "progress",
            "inspections",
            "site_environment",
            "maintenance",
            "equipment",
            "security",
            "land_change",
            "inventory",
        ),
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

    requested_sectors = normalize_public_sector_values(sectors)
    if not requested_sectors and sector_focus:
        requested_sectors = normalize_public_sector_values(sector_focus)
    if not requested_sectors:
        requested_sectors = [profile.default_sector]
    if any(
        s not in PUBLIC_SECTORS or s not in profile.allowed_sectors
        for s in requested_sectors
    ):
        raise ValueError("Invalid sector for customer_type")

    requested_use_cases = list(
        dict.fromkeys(
            str(u).strip().lower() for u in (use_cases or []) if str(u).strip()
        )
    )
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
