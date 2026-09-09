"""Environmental monitoring sector boundary."""

from app.sectors.contracts import SectorModule

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
)

__all__ = ["definition"]
