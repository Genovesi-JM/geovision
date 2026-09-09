"""Organizations and workspace membership domain boundary."""

from app.modules.contracts import DomainModule, RouterMount

definition = DomainModule(
    name="organizations",
    purpose="Customer workspaces, organizations, memberships, and access context.",
    maturity="implemented-transitional",
    routes=(
        RouterMount("organizations.accounts", "organizations", "app.routers.accounts", 40),
        RouterMount(
            "organizations.customer_accounts",
            "organizations",
            "app.routers.customer_accounts",
            90,
            prefix="/accounts/customers",
            tags=("accounts",),
        ),
    ),
)

__all__ = ["definition"]
