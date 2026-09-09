"""Payment and entitlement boundary."""

from app.modules.contracts import DomainModule, RouterMount

definition = DomainModule(
    name="billing",
    purpose="Payment attempts, reconciliation, refunds, and entitlements.",
    maturity="implemented-transitional",
    routes=(
        RouterMount("billing.payments", "billing", "app.routers.payments", 130),
    ),
)

__all__ = ["definition"]
