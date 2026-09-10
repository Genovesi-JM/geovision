"""Activated Mining and Quarry sector package."""

from app.core.routing import RouterMount
from app.sectors.contracts import SectorModule

from .domain import SUPPORTED_ASSET_TYPES, SUPPORTED_DATASET_TYPES, register_mining
from .reporting import register_mining_report_context


register_mining()
register_mining_report_context()

definition = SectorModule(
    name="mining",
    display_name="Mining and Quarry",
    activation_phase=30,
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
    legacy_identifiers=("mining", "quarry"),
    enabled_by_default=True,
    asset_types=tuple(sorted(SUPPORTED_ASSET_TYPES)),
    dataset_types=tuple(sorted(SUPPORTED_DATASET_TYPES)),
    routes=(
        RouterMount(
            "sector.mining",
            "analytics",
            "app.sectors.mining.router",
            71,
            secondary_owners=(
                "actions",
                "assets",
                "datasets",
                "missions",
                "processing",
                "reports",
            ),
        ),
    ),
)

__all__ = ["definition", "register_mining", "register_mining_report_context"]
