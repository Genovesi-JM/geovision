"""Activated Environmental monitoring sector package."""

from app.core.routing import RouterMount
from app.sectors.contracts import SectorModule

from .domain import (
    SUPPORTED_ASSET_TYPES,
    SUPPORTED_DATASET_TYPES,
    register_environmental,
)
from .reporting import register_environmental_report_context


register_environmental()
register_environmental_report_context()

definition = SectorModule(
    name="environmental",
    display_name="Environmental",
    activation_phase=29,
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
    legacy_identifiers=("environment", "ambiental"),
    enabled_by_default=True,
    asset_types=tuple(sorted(SUPPORTED_ASSET_TYPES)),
    dataset_types=tuple(sorted(SUPPORTED_DATASET_TYPES)),
    routes=(
        RouterMount(
            "sector.environmental",
            "analytics",
            "app.sectors.environmental.router",
            69,
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

__all__ = [
    "definition",
    "register_environmental",
    "register_environmental_report_context",
]
