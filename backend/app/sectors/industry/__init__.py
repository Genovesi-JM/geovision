"""Industry, Energy and Utilities capability package."""

from app.core.routing import RouterMount
from app.sectors.contracts import SectorModule

from .domain import (
    SUPPORTED_ASSET_TYPES,
    SUPPORTED_DATASET_TYPES,
    register_industry,
)


register_industry()


definition = SectorModule(
    name="industry_energy_utilities",
    display_name="Industry, Energy and Utilities",
    activation_phase=34,
    module_dependencies=(
        "assets",
        "catalog",
        "operations",
        "missions",
        "datasets",
        "processing",
        "analytics",
        "monitoring",
        "actions",
        "reports",
    ),
    legacy_identifiers=("industry", "industrial", "energy", "utilities", "solar"),
    enabled_by_default=True,
    asset_types=tuple(sorted(SUPPORTED_ASSET_TYPES)),
    dataset_types=tuple(sorted(SUPPORTED_DATASET_TYPES)),
    routes=(
        RouterMount(
            "sector.industry_energy_utilities",
            "analytics",
            "app.sectors.industry.router",
            72,
            secondary_owners=(
                "actions",
                "assets",
                "datasets",
                "monitoring",
                "reports",
            ),
        ),
    ),
)

__all__ = ["definition", "register_industry"]
