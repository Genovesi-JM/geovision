"""Agriculture and agropecuaria sector boundary."""

from app.sectors.contracts import SectorModule

definition = SectorModule(
    name="agriculture",
    display_name="Agriculture and Agropecuaria",
    activation_phase=18,
    module_dependencies=(
        "assets",
        "catalog",
        "datasets",
        "analytics",
        "monitoring",
        "actions",
        "reports",
    ),
    legacy_identifiers=("agro", "agriculture", "livestock"),
)

__all__ = ["definition"]
