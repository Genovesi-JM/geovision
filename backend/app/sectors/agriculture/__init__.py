"""Activated Agriculture and agropecuaria sector package."""

from app.core.routing import RouterMount
from app.sectors.contracts import SectorModule

from .domain import (
    SUPPORTED_ASSET_TYPES,
    SUPPORTED_DATASET_TYPES,
    register_agriculture,
)


register_agriculture()

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
    enabled_by_default=True,
    asset_types=tuple(sorted(SUPPORTED_ASSET_TYPES)),
    dataset_types=tuple(sorted(SUPPORTED_DATASET_TYPES)),
    routes=(
        RouterMount(
            "sector.agriculture",
            "analytics",
            "app.sectors.agriculture.router",
            64,
            secondary_owners=("actions", "assets", "datasets", "monitoring", "reports"),
        ),
    ),
)

__all__ = ["definition", "register_agriculture"]
