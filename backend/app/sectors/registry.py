"""Validated registry of GeoVision's independently activatable sectors."""

from app.modules.registry import DOMAIN_MODULES_BY_NAME

from .agriculture import definition as agriculture
from .contracts import SectorModule
from .environmental import definition as environmental
from .infrastructure import definition as infrastructure
from .industry import definition as industry
from .mining import definition as mining
from .ports import definition as ports

REQUIRED_SECTOR_NAMES = (
    "agriculture",
    "infrastructure",
    "environmental",
    "mining",
    "industry_energy_utilities",
    "ports_logistics",
)

SECTOR_MODULES: tuple[SectorModule, ...] = (
    agriculture,
    infrastructure,
    environmental,
    mining,
    industry,
    ports,
)
SECTOR_MODULES_BY_NAME = {sector.name: sector for sector in SECTOR_MODULES}
SECTOR_HTTP_ROUTES = tuple(
    sorted(
        (
            route
            for sector in SECTOR_MODULES
            if sector.enabled_by_default
            for route in sector.routes
        ),
        key=lambda route: route.order,
    )
)


def validate_sector_registry() -> None:
    names = tuple(sector.name for sector in SECTOR_MODULES)
    if names != REQUIRED_SECTOR_NAMES:
        raise ValueError(
            f"Sector registry mismatch: expected {REQUIRED_SECTOR_NAMES}, got {names}"
        )
    if len(set(names)) != len(names):
        raise ValueError("Sector module names must be unique")

    known_modules = set(DOMAIN_MODULES_BY_NAME)
    for sector in SECTOR_MODULES:
        unknown = set(sector.module_dependencies) - known_modules
        if unknown:
            raise ValueError(
                f"{sector.name} depends on unknown modules: {sorted(unknown)}"
            )
    route_keys = [route.key for route in SECTOR_HTTP_ROUTES]
    route_orders = [route.order for route in SECTOR_HTTP_ROUTES]
    route_targets = [
        (route.import_path, route.attribute) for route in SECTOR_HTTP_ROUTES
    ]
    if len(set(route_keys)) != len(route_keys):
        raise ValueError("Sector router keys must be unique")
    if len(set(route_orders)) != len(route_orders):
        raise ValueError("Sector router registration orders must be unique")
    if len(set(route_targets)) != len(route_targets):
        raise ValueError("A sector router target may be mounted only once")


validate_sector_registry()

__all__ = [
    "REQUIRED_SECTOR_NAMES",
    "SECTOR_MODULES",
    "SECTOR_MODULES_BY_NAME",
    "SECTOR_HTTP_ROUTES",
    "validate_sector_registry",
]
