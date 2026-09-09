"""Infrastructure sector boundary, including construction compatibility."""

from app.sectors.contracts import SectorModule

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
)

__all__ = ["definition"]
