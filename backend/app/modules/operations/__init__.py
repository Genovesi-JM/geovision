"""Internal and customer-facing operational orchestration boundary."""

from app.modules.contracts import DomainModule, RouterMount

definition = DomainModule(
    name="operations",
    purpose="Service delivery, internal resources, inspections, and operations facades.",
    maturity="implemented-transitional",
    routes=(
        RouterMount(
            "operations.experience",
            "operations",
            "app.routers.operations_experience",
            84,
            secondary_owners=(
                "organizations",
                "assets",
                "orders",
                "missions",
                "processing",
                "reports",
                "catalog",
                "billing",
                "audit",
            ),
        ),
        RouterMount(
            "operations.resources",
            "operations",
            "app.routers.operations_resources",
            85,
            secondary_owners=("catalog", "orders", "audit"),
        ),
        RouterMount(
            "operations.fulfilment_jobs",
            "operations",
            "app.routers.fulfilment_jobs",
            87,
            secondary_owners=("orders", "assets", "audit"),
        ),
        RouterMount(
            "operations.admin",
            "operations",
            "app.routers.admin",
            140,
            secondary_owners=("audit", "assets", "catalog", "datasets", "orders"),
        ),
        RouterMount(
            "operations.mobile",
            "operations",
            "app.routers.mobile",
            170,
            secondary_owners=(
                "actions",
                "assets",
                "audit",
                "billing",
                "missions",
                "orders",
                "organizations",
                "reports",
            ),
        ),
        RouterMount(
            "operations.construction",
            "operations",
            "app.routers.construction",
            210,
            secondary_owners=("assets", "reports"),
        ),
    ),
)

__all__ = ["definition"]
