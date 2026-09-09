"""Notification, contact-channel, and delivery-status boundary."""

from app.modules.contracts import DomainModule, RouterMount

definition = DomainModule(
    name="notifications",
    purpose="Notification intents, channels, delivery, and customer contact methods.",
    maturity="partial",
    routes=(
        RouterMount("notifications.contacts", "notifications", "app.routers.contacts", 160),
    ),
)

__all__ = ["definition"]
