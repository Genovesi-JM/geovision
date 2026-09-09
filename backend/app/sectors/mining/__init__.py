"""Mining and quarry sector boundary."""

from app.sectors.contracts import SectorModule

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
    legacy_identifiers=("mining", "industry"),
)

__all__ = ["definition"]
