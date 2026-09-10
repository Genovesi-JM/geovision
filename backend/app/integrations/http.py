"""HTTP compatibility mounts for existing external integrations."""

from app.core.routing import RouterMount

INTEGRATION_HTTP_ROUTES = (
    RouterMount(
        key="integrations.erp",
        owner="integrations",
        import_path="app.routers.integrations",
        order=180,
    ),
    RouterMount(
        key="integrations.events",
        owner="integrations",
        import_path="app.routers.events",
        order=181,
    ),
    RouterMount(
        key="integrations.connection_registry",
        owner="integrations",
        import_path="app.routers.integration_connections",
        order=182,
    ),
)

__all__ = ["INTEGRATION_HTTP_ROUTES"]
