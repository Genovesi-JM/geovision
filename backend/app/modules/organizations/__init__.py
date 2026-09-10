"""Organizations and workspace membership domain boundary."""

from app.modules.contracts import DomainModule, RouterMount

definition = DomainModule(
    name="organizations",
    purpose="Customer workspaces, organizations, memberships, and access context.",
    maturity="implemented",
    routes=(
        RouterMount(
            "organizations.canonical",
            "organizations",
            "app.routers.organizations",
            35,
        ),
        RouterMount(
            "organizations.invitations",
            "organizations",
            "app.routers.invitations",
            37,
            secondary_owners=("identity",),
        ),
        RouterMount("organizations.accounts", "organizations", "app.routers.accounts", 40),
    ),
)

__all__ = ["definition"]
