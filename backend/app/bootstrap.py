"""Application composition root for domains, integrations, and transports."""

from __future__ import annotations

from importlib import import_module

from fastapi import APIRouter, FastAPI

from app.core.routing import RouterMount
from app.integrations.http import INTEGRATION_HTTP_ROUTES
from app.modules.registry import DOMAIN_HTTP_ROUTES


def application_route_mounts() -> tuple[RouterMount, ...]:
    """Return every current router once, in its legacy registration order."""

    mounts = tuple(
        sorted(
            (*DOMAIN_HTTP_ROUTES, *INTEGRATION_HTTP_ROUTES),
            key=lambda item: item.order,
        )
    )
    keys = [mount.key for mount in mounts]
    orders = [mount.order for mount in mounts]
    targets = [(mount.import_path, mount.attribute) for mount in mounts]
    if len(set(keys)) != len(keys):
        raise ValueError("Application router keys must be unique")
    if len(set(orders)) != len(orders):
        raise ValueError("Application router registration orders must be unique")
    if len(set(targets)) != len(targets):
        raise ValueError("A router target may be registered only once")
    return mounts


def register_application_routes(application: FastAPI) -> None:
    """Mount legacy route implementations through explicit module ownership."""

    for mount in application_route_mounts():
        module = import_module(mount.import_path)
        router = getattr(module, mount.attribute)
        if not isinstance(router, APIRouter):
            raise TypeError(
                f"{mount.import_path}.{mount.attribute} is not a FastAPI APIRouter"
            )

        kwargs: dict[str, object] = {}
        if mount.prefix:
            kwargs["prefix"] = mount.prefix
        if mount.tags:
            kwargs["tags"] = list(mount.tags)
        application.include_router(router, **kwargs)


__all__ = ["application_route_mounts", "register_application_routes"]
