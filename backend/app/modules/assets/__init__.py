"""Cross-sector asset domain boundary; the generic model belongs to Phase 5."""

from app.modules.contracts import DomainModule, RouterMount

definition = DomainModule(
    name="assets",
    purpose="Sites, physical assets, asset hierarchy, and spatial identity.",
    maturity="partial",
    routes=(
        RouterMount(
            "assets.projects",
            "assets",
            "app.routers.projects",
            20,
            prefix="/projects",
            tags=("projects",),
            secondary_owners=("operations",),
        ),
    ),
)

__all__ = ["definition"]
