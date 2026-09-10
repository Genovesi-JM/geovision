"""IoT monitoring, telemetry, alert, and device-state boundary."""

from app.modules.contracts import DomainModule, RouterMount

definition = DomainModule(
    name="monitoring",
    purpose=(
        "Assigned devices, edge/cloud telemetry, alerts, satellite/weather "
        "intelligence, live events, and health."
    ),
    maturity="implemented",
    dependencies=("core", "organizations", "assets", "missions", "datasets"),
    routes=(
        RouterMount(
            "monitoring.intelligence",
            "monitoring",
            "app.routers.intelligence",
            114,
            secondary_owners=("assets", "datasets", "missions"),
        ),
        RouterMount(
            "monitoring.iot",
            "monitoring",
            "app.routers.iot",
            190,
            secondary_owners=("actions", "assets", "audit", "reports"),
        ),
        RouterMount(
            "monitoring.mobile",
            "monitoring",
            "app.routers.iot",
            200,
            attribute="mobile_router",
        ),
    ),
)

__all__ = ["definition"]
