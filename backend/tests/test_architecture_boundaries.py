"""Phase 1 modular-monolith structure and compatibility contracts."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

from fastapi.routing import APIWebSocketRoute

from app.bootstrap import application_route_mounts
from app.modules.registry import (
    DOMAIN_MODULES,
    REQUIRED_DOMAIN_NAMES,
    routes_for_module,
    validate_domain_registry,
)
from app.sectors.registry import (
    REQUIRED_SECTOR_NAMES,
    SECTOR_MODULES,
    validate_sector_registry,
)

APP_ROOT = Path(__file__).resolve().parents[1] / "app"
GENERATED_DOC_PATHS = {"/docs", "/docs/oauth2-redirect", "/openapi.json", "/redoc"}
PHASE_13_ROUTE_COUNT = 299
PHASE_13_ROUTE_SHA256 = "f2ce2244de196184c53fc56b2ca7e5d78350266f1a707d5da3320b5b4ec51974"


def _route_contract(application) -> list[str]:
    rows: list[str] = []
    for route in application.routes:
        if route.path in GENERATED_DOC_PATHS:
            continue
        methods = sorted((getattr(route, "methods", None) or set()) - {"HEAD", "OPTIONS"})
        if methods:
            rows.extend(f"{method} {route.path}" for method in methods)
        elif isinstance(route, APIWebSocketRoute):
            rows.append(f"WEBSOCKET {route.path}")
    return sorted(rows)


def _import_targets(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level
            if node.module:
                targets.add(f"{prefix}{node.module}")
            else:
                targets.update(f"{prefix}{alias.name}" for alias in node.names)
    return targets


def test_phase_13_http_and_websocket_contract_is_pinned(client):
    routes = _route_contract(client.app)
    payload = "\n".join(routes).encode()

    assert len(routes) == PHASE_13_ROUTE_COUNT, "\n".join(routes)
    assert len(routes) == len(set(routes)), "duplicate method/path registration detected"
    assert hashlib.sha256(payload).hexdigest() == PHASE_13_ROUTE_SHA256, "\n".join(routes)


def test_application_mount_order_preserves_legacy_router_order():
    assert [mount.key for mount in application_route_mounts()] == [
        "identity.auth",
        "assets.projects",
        "assets.canonical",
        "analytics.ai",
        "organizations.canonical",
        "organizations.invitations",
        "organizations.accounts",
        "identity.me",
        "analytics.kpi",
        "catalog.canonical",
        "catalog.products",
        "orders.legacy",
        "orders.canonical",
        "operations.resources",
        "operations.fulfilment_jobs",
        "missions.canonical",
        "organizations.customer_accounts",
        "operations.employees",
        "datasets.api",
        "analytics.risk",
        "billing.payments",
        "operations.admin",
        "catalog.shop",
        "notifications.contacts",
        "operations.mobile",
        "integrations.erp",
        "integrations.events",
        "monitoring.iot",
        "monitoring.mobile",
        "operations.construction",
    ]


def test_required_domain_and_sector_boundaries_are_registered():
    validate_domain_registry()
    validate_sector_registry()

    assert tuple(module.name for module in DOMAIN_MODULES) == REQUIRED_DOMAIN_NAMES
    assert tuple(sector.name for sector in SECTOR_MODULES) == REQUIRED_SECTOR_NAMES
    assert all(sector.enabled_by_default is False for sector in SECTOR_MODULES)
    assert routes_for_module("missions")
    assert routes_for_module("reports")


def test_core_and_common_modules_follow_dependency_direction():
    forbidden_from_core = (
        "app.integrations",
        "app.models",
        "app.modules",
        "app.routers",
        "app.sectors",
        "app.workers",
    )
    forbidden_relative_core = (
        "integrations",
        "models",
        "modules",
        "routers",
        "sectors",
        "workers",
    )
    for path in (APP_ROOT / "core").glob("*.py"):
        for target in _import_targets(path):
            assert not target.startswith(forbidden_from_core), f"{path}: forbidden import {target}"
            if target.startswith("."):
                assert not target.lstrip(".").startswith(forbidden_relative_core), (
                    f"{path}: forbidden relative import {target}"
                )

    for path in (APP_ROOT / "modules").rglob("*.py"):
        for target in _import_targets(path):
            assert not target.startswith("app.sectors"), f"{path}: common module imports sector {target}"
            assert not target.startswith("app.routers"), f"{path}: domain module imports router {target}"
            if target.startswith("."):
                assert not target.lstrip(".").startswith("sectors"), (
                    f"{path}: common module imports sector {target}"
                )
                assert not target.lstrip(".").startswith("routers"), (
                    f"{path}: domain module imports router {target}"
                )


def test_routers_do_not_import_other_routers():
    for path in (APP_ROOT / "routers").glob("*.py"):
        for target in _import_targets(path):
            assert not target.startswith("app.routers"), f"{path}: router-to-router import {target}"
            assert not (target.startswith(".") and not target.startswith("..")), (
                f"{path}: router-to-router relative import {target}"
            )


def test_legacy_shared_imports_resolve_to_canonical_core_objects():
    import app.config as legacy_config
    import app.crypto as legacy_encryption
    import app.database as legacy_database
    import app.oauth2 as legacy_tokens
    import app.time_utils as legacy_time
    import app.utils as legacy_passwords
    from app.core import database
    from app.core import encryption, passwords, time, tokens
    from app.core.config import settings

    assert legacy_config.settings is settings
    assert legacy_database.Base is database.Base
    assert legacy_database.engine is database.engine
    assert legacy_database.SessionLocal is database.SessionLocal
    assert legacy_tokens.create_access_token is tokens.create_access_token
    assert legacy_passwords.hash_password is passwords.hash_password
    assert legacy_time.utc_now is time.utc_now
    assert legacy_encryption.encrypt is encryption.encrypt


def test_core_event_and_observability_contracts_are_provider_neutral():
    from app.core.events import DomainEvent, NullEventPublisher
    from app.core.observability import get_logger

    source_payload = {"source": "test"}
    event = DomainEvent(
        name="dataset.created",
        aggregate_type="dataset",
        aggregate_id="dataset-1",
        payload=source_payload,
    )
    assert event.aggregate_id == "dataset-1"
    assert NullEventPublisher().publish(event) is None
    assert get_logger("modules.datasets").name == "app.modules.datasets"

    source_payload["source"] = "changed"
    assert event.payload["source"] == "test"
    with pytest.raises(TypeError):
        event.payload["source"] = "changed"
    with pytest.raises(AttributeError):
        event.name = "dataset.changed"
