"""Notification, contact-channel, and delivery-status boundary."""

from app.modules.contracts import DomainModule, RouterMount

definition = DomainModule(
    name="notifications",
    purpose="Contextual in-app inbox, preferences, endpoints, and durable delivery.",
    maturity="implemented",
    dependencies=("core", "identity", "organizations", "assets", "orders", "actions", "reports"),
    routes=(
        RouterMount(
            "notifications.canonical",
            "notifications",
            "app.routers.notifications",
            67,
            secondary_owners=("identity", "organizations", "assets", "orders", "actions", "reports"),
        ),
        RouterMount("notifications.contacts", "notifications", "app.routers.contacts", 160),
    ),
)

__all__ = ["definition"]
