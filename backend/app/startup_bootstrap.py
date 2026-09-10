"""Idempotent legacy/reference-data bootstrap owned by one startup process."""

from __future__ import annotations

import logging

from .core import database
from .core.integration import sanitize_integration_message
from .core.observability import get_logger, log_event
from .modules.catalog.services import sync_catalog_from_legacy
from .sectors.services import sync_enabled_sector_definitions
from .seed_data import seed_admin_users
from .services.cart import seed_kit_products, seed_shop_products


logger = get_logger(__name__)


class StartupBootstrapError(RuntimeError):
    """A sanitized fatal error raised by the one-shot deployment job."""


def run_compatibility_bootstrap(*, strict: bool = False) -> None:
    """Apply the existing best-effort repair and reference-data bootstrap."""

    try:
        database.ensure_legacy_schema()
        log_event(logger, logging.INFO, "database.schema_drift_check.completed")
    except Exception as exc:
        log_event(
            logger,
            logging.WARNING,
            "database.schema_drift_check.failed",
            error=sanitize_integration_message(exc),
        )
        if strict:
            raise StartupBootstrapError(
                "legacy schema compatibility bootstrap failed"
            ) from None

    try:
        db = database.SessionLocal()
        try:
            sync_enabled_sector_definitions(db)
            seed_shop_products(db)
            seed_kit_products(db)
            sync_catalog_from_legacy(db)
            inserted_users = seed_admin_users()
            if inserted_users:
                log_event(
                    logger,
                    logging.INFO,
                    "application.admin_seed.completed",
                    inserted_users=inserted_users,
                )
        finally:
            db.close()
    except Exception as exc:
        log_event(
            logger,
            logging.WARNING,
            "application.seed.failed",
            error=sanitize_integration_message(exc),
        )
        if strict:
            raise StartupBootstrapError("reference-data bootstrap failed") from None


__all__ = ["StartupBootstrapError", "run_compatibility_bootstrap"]
