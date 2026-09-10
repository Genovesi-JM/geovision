"""Recommended and assigned action boundary."""

from app.modules.contracts import DomainModule, RouterMount

definition = DomainModule(
    name="actions",
    purpose="Validated recommendations, commands, assignments, and outcome tracking.",
    maturity="implemented",
    dependencies=("core", "organizations", "assets", "analytics", "catalog"),
    routes=(
        RouterMount(
            "actions.canonical",
            "actions",
            "app.routers.actions",
            63,
            secondary_owners=("analytics", "assets", "audit", "catalog"),
        ),
    ),
)

__all__ = ["definition"]
