"""Provider-neutral data-acquisition mission boundary."""

from app.modules.contracts import DomainModule, RouterMount

definition = DomainModule(
    name="missions",
    purpose="Acquisition missions, aircraft assignments, approvals, and results.",
    maturity="implemented",
    dependencies=("core", "assets", "orders", "operations"),
    routes=(
        RouterMount(
            "missions.canonical",
            "missions",
            "app.routers.acquisitions",
            88,
            secondary_owners=("assets", "datasets", "operations"),
        ),
    ),
)

__all__ = ["definition"]
