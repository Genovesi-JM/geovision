"""Payment and entitlement boundary."""

from app.modules.contracts import DomainModule, RouterMount

definition = DomainModule(
    name="billing",
    purpose=(
        "Payment attempts, reconciliation, refunds, entitlements, and private "
        "unit economics."
    ),
    maturity="implemented-transitional",
    routes=(
        RouterMount("billing.payments", "billing", "app.routers.payments", 130),
        RouterMount(
            "billing.economics",
            "billing",
            "app.routers.economics",
            131,
            secondary_owners=("orders", "catalog", "operations", "audit"),
        ),
    ),
)

__all__ = ["definition"]
