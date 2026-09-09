"""Internal and customer-facing operational orchestration boundary."""

from app.modules.contracts import DomainModule, RouterMount

definition = DomainModule(
    name="operations",
    purpose="Service delivery, internal resources, inspections, and operations facades.",
    maturity="implemented-transitional",
    routes=(
        RouterMount(
            "operations.resources",
            "operations",
            "app.routers.operations_resources",
            85,
            secondary_owners=("catalog", "orders", "audit"),
        ),
        RouterMount(
            "operations.employees",
            "operations",
            "app.routers.employees",
            100,
            prefix="/accounts/employees",
            tags=("accounts",),
            secondary_owners=("organizations",),
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
            secondary_owners=("actions", "assets", "audit", "billing", "missions"),
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
