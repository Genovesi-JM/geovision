"""Customer web-portal projection boundary, separate from internal Operations."""

from app.modules.contracts import DomainModule, RouterMount


definition = DomainModule(
    name="customer_portal",
    purpose=(
        "Tenant-safe customer web navigation, portfolio summaries, and map "
        "projections."
    ),
    maturity="implemented",
    dependencies=(
        "core",
        "organizations",
        "assets",
        "analytics",
        "actions",
        "catalog",
        "orders",
        "monitoring",
        "reports",
        "billing",
    ),
    routes=(
        RouterMount(
            "customer_portal.experience",
            "customer_portal",
            "app.routers.customer_portal",
            172,
            secondary_owners=(
                "organizations",
                "assets",
                "analytics",
                "actions",
                "catalog",
                "orders",
                "monitoring",
                "reports",
                "billing",
            ),
        ),
    ),
)


__all__ = ["definition"]
