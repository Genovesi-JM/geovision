"""Cross-sector spatial asset domain boundary."""

from app.modules.contracts import DomainModule, RouterMount

definition = DomainModule(
    name="assets",
    purpose="Sites, physical assets, asset hierarchy, and spatial identity.",
    maturity="implemented",
    routes=(
        RouterMount(
            "assets.canonical",
            "assets",
            "app.routers.assets",
            25,
        ),
        RouterMount(
            "assets.location",
            "assets",
            "app.routers.location",
            26,
        ),
    ),
)

__all__ = ["definition"]
