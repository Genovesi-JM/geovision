"""First-party product and service catalogue boundary."""

from app.modules.contracts import DomainModule, RouterMount

definition = DomainModule(
    name="catalog",
    purpose="GeoVision-owned products, services, kits, pricing, and availability.",
    maturity="implemented-transitional",
    routes=(
        RouterMount(
            "catalog.canonical",
            "catalog",
            "app.routers.catalog",
            65,
        ),
        RouterMount(
            "catalog.products",
            "catalog",
            "app.routers.products",
            70,
            prefix="/products",
            tags=("products",),
        ),
        RouterMount(
            "catalog.shop",
            "catalog",
            "app.routers.shop",
            150,
            secondary_owners=("orders", "billing", "actions", "operations"),
        ),
    ),
)

__all__ = ["definition"]
