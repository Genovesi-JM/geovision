"""Activated Ports and Logistics sector package."""

from app.core.routing import RouterMount
from app.sectors.contracts import SectorModule

from .domain import SUPPORTED_ASSET_TYPES, SUPPORTED_DATASET_TYPES, register_ports
from .reporting import register_ports_report_context


register_ports()
register_ports_report_context()

definition = SectorModule(
    name="ports_logistics",
    display_name="Ports and Logistics",
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
    legacy_identifiers=("ports_logistics", "ports", "logistics", "ports_industrial"),
    enabled_by_default=True,
    asset_types=tuple(sorted(SUPPORTED_ASSET_TYPES)),
    dataset_types=tuple(sorted(SUPPORTED_DATASET_TYPES)),
    routes=(
        RouterMount(
            "sector.ports_logistics",
            "analytics",
            "app.sectors.ports.router",
            73,
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
