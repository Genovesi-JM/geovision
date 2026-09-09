"""IoT monitoring, telemetry, alert, and device-state boundary."""

from app.modules.contracts import DomainModule, RouterMount

definition = DomainModule(
    name="monitoring",
    purpose="Devices, gateways, telemetry, alert rules, live events, and health.",
    maturity="implemented-transitional",
    routes=(
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
