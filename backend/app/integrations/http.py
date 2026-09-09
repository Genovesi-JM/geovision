"""HTTP compatibility mounts for existing external integrations."""

from app.core.routing import RouterMount

INTEGRATION_HTTP_ROUTES = (
    RouterMount(
        key="integrations.erp",
        owner="integrations",
        import_path="app.routers.integrations",
        order=180,
    ),
)

__all__ = ["INTEGRATION_HTTP_ROUTES"]
