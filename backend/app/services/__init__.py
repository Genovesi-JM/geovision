"""Lazy, backward-compatible exports for GeoVision service facades."""

from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORT_MODULES = {
    "get_storage_service": "app.services.storage",
    "StorageService": "app.services.storage",
    "get_payment_orchestrator": "app.services.payments",
    "PaymentOrchestrator": "app.services.payments",
    "get_risk_engine": "app.services.risk_engine",
    "RiskEngine": "app.services.risk_engine",
}

__all__ = list(_EXPORT_MODULES)


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *__all__})
