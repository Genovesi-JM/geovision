"""Activated Infrastructure sector, including construction compatibility."""

from app.core.routing import RouterMount
from app.sectors.contracts import SectorModule

from .domain import (
    SUPPORTED_ASSET_TYPES,
    SUPPORTED_DATASET_TYPES,
    register_infrastructure,
)
from .reporting import register_infrastructure_report_context


register_infrastructure()
register_infrastructure_report_context()

definition = SectorModule(
    name="infrastructure",
    display_name="Infrastructure",
    activation_phase=28,
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
    legacy_identifiers=("infrastructure", "construction"),
    enabled_by_default=True,
    asset_types=tuple(sorted(SUPPORTED_ASSET_TYPES)),
    dataset_types=tuple(sorted(SUPPORTED_DATASET_TYPES)),
    routes=(
        RouterMount(
            "sector.infrastructure",
            "analytics",
            "app.sectors.infrastructure.router",
            68,
            secondary_owners=("actions", "assets", "datasets", "processing", "reports"),
        ),
    ),
)

__all__ = [
    "definition",
    "register_infrastructure",
    "register_infrastructure_report_context",
]
