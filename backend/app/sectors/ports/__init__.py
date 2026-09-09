"""Ports and industrial sector boundary."""

from app.sectors.contracts import SectorModule

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
)

__all__ = ["definition"]
