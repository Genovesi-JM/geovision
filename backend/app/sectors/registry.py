"""Validated registry of GeoVision's independently activatable sectors."""

from app.modules.registry import DOMAIN_MODULES_BY_NAME

from .agriculture import definition as agriculture
from .contracts import SectorModule
from .environmental import definition as environmental
from .infrastructure import definition as infrastructure
from .mining import definition as mining
from .ports import definition as ports

REQUIRED_SECTOR_NAMES = (
    "agriculture",
    "infrastructure",
    "environmental",
    "mining",
    "ports",
)

SECTOR_MODULES: tuple[SectorModule, ...] = (
    agriculture,
    infrastructure,
    environmental,
    mining,
    ports,
)
SECTOR_MODULES_BY_NAME = {sector.name: sector for sector in SECTOR_MODULES}


def validate_sector_registry() -> None:
    names = tuple(sector.name for sector in SECTOR_MODULES)
    if names != REQUIRED_SECTOR_NAMES:
        raise ValueError(f"Sector registry mismatch: expected {REQUIRED_SECTOR_NAMES}, got {names}")
    if len(set(names)) != len(names):
        raise ValueError("Sector module names must be unique")

    known_modules = set(DOMAIN_MODULES_BY_NAME)
    for sector in SECTOR_MODULES:
        unknown = set(sector.module_dependencies) - known_modules
        if unknown:
            raise ValueError(f"{sector.name} depends on unknown modules: {sorted(unknown)}")


validate_sector_registry()

__all__ = [
    "REQUIRED_SECTOR_NAMES",
    "SECTOR_MODULES",
    "SECTOR_MODULES_BY_NAME",
    "validate_sector_registry",
]
