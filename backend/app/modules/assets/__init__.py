"""Cross-sector spatial asset domain boundary."""

from app.modules.contracts import DomainModule, RouterMount

definition = DomainModule(
    name="assets",
    purpose="Sites, physical assets, asset hierarchy, and spatial identity.",
    maturity="implemented",
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
        RouterMount(
            "assets.canonical",
            "assets",
            "app.routers.assets",
            25,
        ),
    ),
)

__all__ = ["definition"]
