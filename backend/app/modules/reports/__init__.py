"""Report drafting, review, publication, and delivery boundary."""

from app.modules.contracts import DomainModule, RouterMount

definition = DomainModule(
    name="reports",
    purpose="Report versions, QA, publication, documents, and customer delivery.",
    maturity="implemented",
    dependencies=(
        "core",
        "organizations",
        "assets",
        "missions",
        "datasets",
        "analytics",
        "actions",
        "audit",
    ),
    routes=(
        RouterMount(
            "reports.canonical",
            "reports",
            "app.routers.reports",
            66,
            secondary_owners=("analytics", "assets", "datasets", "audit"),
        ),
    ),
)

__all__ = ["definition"]
