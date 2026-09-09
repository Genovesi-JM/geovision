"""Customer order and commercial lifecycle boundary."""

from app.modules.contracts import DomainModule, RouterMount

definition = DomainModule(
    name="orders",
    purpose="Carts, orders, order items, deliverables, and lifecycle events.",
    maturity="implemented-transitional",
    routes=(
        RouterMount(
            "orders.legacy",
            "orders",
            "app.routers.orders",
            80,
            prefix="/orders",
            tags=("orders",),
        ),
        RouterMount(
            "orders.canonical",
            "orders",
            "app.routers.commercial_orders",
            82,
        ),
    ),
)

__all__ = ["definition"]
