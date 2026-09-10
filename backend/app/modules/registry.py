"""Validated registry for GeoVision's common domain modules."""

from __future__ import annotations

from collections.abc import Iterable

from app.core.routing import RouterMount

from .actions import definition as actions
from .analytics import definition as analytics
from .assets import definition as assets
from .audit import definition as audit
from .billing import definition as billing
from .catalog import definition as catalog
from .contracts import DomainModule
from .customer_portal import definition as customer_portal
from .datasets import definition as datasets
from .identity import definition as identity
from .missions import definition as missions
from .monitoring import definition as monitoring
from .notifications import definition as notifications
from .operations import definition as operations
from .orders import definition as orders
from .organizations import definition as organizations
from .processing import definition as processing
from .reports import definition as reports

REQUIRED_DOMAIN_NAMES = (
    "identity",
    "organizations",
    "assets",
    "catalog",
    "orders",
    "operations",
    "missions",
    "datasets",
    "processing",
    "analytics",
    "monitoring",
    "actions",
    "reports",
    "notifications",
    "billing",
    "audit",
    "customer_portal",
)

DOMAIN_MODULES: tuple[DomainModule, ...] = (
    identity,
    organizations,
    assets,
    catalog,
    orders,
    operations,
    missions,
    datasets,
    processing,
    analytics,
    monitoring,
    actions,
    reports,
    notifications,
    billing,
    audit,
    customer_portal,
)

DOMAIN_MODULES_BY_NAME = {module.name: module for module in DOMAIN_MODULES}
DOMAIN_HTTP_ROUTES = tuple(
    sorted(
        (route for module in DOMAIN_MODULES for route in module.routes),
        key=lambda route: route.order,
    )
)


def routes_for_module(name: str) -> tuple[RouterMount, ...]:
    """Return primary and compatibility-facade routes touching one domain."""

    if name not in DOMAIN_MODULES_BY_NAME:
        raise KeyError(f"Unknown GeoVision domain module: {name}")
    return tuple(
        route
        for route in DOMAIN_HTTP_ROUTES
        if route.owner == name or name in route.secondary_owners
    )


def _assert_acyclic(modules: Iterable[DomainModule]) -> None:
    graph = {
        module.name: tuple(dep for dep in module.dependencies if dep != "core")
        for module in modules
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visiting:
            raise ValueError(f"Circular domain dependency detected at {name}")
        if name in visited:
            return
        visiting.add(name)
        for dependency in graph[name]:
            visit(dependency)
        visiting.remove(name)
        visited.add(name)

    for module_name in graph:
        visit(module_name)


def validate_domain_registry() -> None:
    """Fail fast when a module or router descriptor breaks architecture rules."""

    names = tuple(module.name for module in DOMAIN_MODULES)
    if names != REQUIRED_DOMAIN_NAMES:
        raise ValueError(f"Domain registry mismatch: expected {REQUIRED_DOMAIN_NAMES}, got {names}")
    if len(set(names)) != len(names):
        raise ValueError("Domain module names must be unique")

    known_dependencies = {"core", *names}
    for module in DOMAIN_MODULES:
        unknown = set(module.dependencies) - known_dependencies
        if unknown:
            raise ValueError(f"{module.name} has unknown dependencies: {sorted(unknown)}")
        if module.name in module.dependencies:
            raise ValueError(f"{module.name} cannot depend on itself")

    keys = [route.key for route in DOMAIN_HTTP_ROUTES]
    orders = [route.order for route in DOMAIN_HTTP_ROUTES]
    targets = [(route.import_path, route.attribute) for route in DOMAIN_HTTP_ROUTES]
    if len(set(keys)) != len(keys):
        raise ValueError("Domain router keys must be unique")
    if len(set(orders)) != len(orders):
        raise ValueError("Domain router registration orders must be unique")
    if len(set(targets)) != len(targets):
        raise ValueError("A legacy router may be mounted only once")

    for route in DOMAIN_HTTP_ROUTES:
        if route.owner not in DOMAIN_MODULES_BY_NAME:
            raise ValueError(f"Router {route.key} has unknown owner {route.owner}")
        unknown_secondary = set(route.secondary_owners) - set(names)
        if unknown_secondary:
            raise ValueError(
                f"Router {route.key} has unknown secondary owners: "
                f"{sorted(unknown_secondary)}"
            )

    _assert_acyclic(DOMAIN_MODULES)


validate_domain_registry()

__all__ = [
    "DOMAIN_HTTP_ROUTES",
    "DOMAIN_MODULES",
    "DOMAIN_MODULES_BY_NAME",
    "REQUIRED_DOMAIN_NAMES",
    "routes_for_module",
    "validate_domain_registry",
]
