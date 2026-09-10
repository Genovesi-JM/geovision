"""Activated Ports and Industrial sector package."""

from app.core.routing import RouterMount
from app.sectors.contracts import SectorModule

from .domain import SUPPORTED_ASSET_TYPES, SUPPORTED_DATASET_TYPES, register_ports
from .reporting import register_ports_report_context


register_ports()
register_ports_report_context()

definition = SectorModule(
    name="ports",
    display_name="Ports and Industrial",
    activation_phase=31,
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
    legacy_identifiers=("ports", "industrial", "industry"),
    enabled_by_default=True,
    asset_types=tuple(sorted(SUPPORTED_ASSET_TYPES)),
    dataset_types=tuple(sorted(SUPPORTED_DATASET_TYPES)),
    routes=(
        RouterMount(
            "sector.ports",
            "analytics",
            "app.sectors.ports.router",
            72,
            secondary_owners=(
                "actions",
                "assets",
                "datasets",
                "missions",
                "monitoring",
                "reports",
            ),
        ),
    ),
)

__all__ = ["definition", "register_ports", "register_ports_report_context"]
