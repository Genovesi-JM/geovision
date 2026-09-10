# backend/app/main.py

from contextlib import asynccontextmanager

import logging
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .bootstrap import register_application_routes
from .core import database
from .core.config import settings
from .core.integration import sanitize_integration_message
from .core.observability import configure_observability, get_logger, log_event
from .middleware import (
    HTTPSRedirectMiddleware,
    RateLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from .seed_data import (
    seed_admin_users,
)
from .services.cart import seed_shop_products, seed_kit_products
from .modules.catalog.services import sync_catalog_from_legacy
from .sectors.services import sync_enabled_sector_definitions
from .workers import application_workers


logger = get_logger(__name__)


@asynccontextmanager
async def application_lifespan(application: FastAPI):
    """Start and stop background IoT services with the FastAPI application."""

    async with application_workers(application):
        yield


def create_application() -> FastAPI:
    """Build and configure the FastAPI instance."""
    observability = configure_observability(settings)
    application = FastAPI(title=settings.app_name, lifespan=application_lifespan)

    # Safe startup diagnostics (no secrets)
    log_event(
        logger,
        logging.INFO,
        "application.configuration.loaded",
        configuration=settings.safe_summary(),
        observability=observability,
    )

    # CORS
    # Note: browsers will reject `Access-Control-Allow-Origin: *` when
    # `allow_credentials=True`, so we must send an explicit origin list.
    default_origins = {
        "http://127.0.0.1:8001",
        "http://localhost:8001",
        "https://genovesi-jm.github.io",
    }
    try:
        parsed = urlparse(settings.frontend_base)
        if parsed.scheme and parsed.netloc:
            default_origins.add(f"{parsed.scheme}://{parsed.netloc}")
    except Exception:
        pass

    if settings.cors_origin_list:
        allow_origins = list(settings.cors_origin_list)
    else:
        allow_origins = sorted(default_origins)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Security middleware (order matters: outermost first)
    application.add_middleware(SecurityHeadersMiddleware)
    application.add_middleware(RateLimitMiddleware)
    application.add_middleware(HTTPSRedirectMiddleware)
    application.add_middleware(RequestContextMiddleware)

    database.init_db_engine()

    # Ensure DB schema is up-to-date (add missing columns)
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

    # Composition is explicit, ordered, and compatibility-preserving. Router
    # implementations remain in place until their owning phases migrate them.
    register_application_routes(application)

    @application.get("/health", tags=["system"])
    def healthcheck() -> dict:
        return {"status": "ok"}

    @application.get("/ready", tags=["system"])
    def readinesscheck() -> dict:
        """Report readiness only when the application can reach its database."""

        try:
            if database.engine is None:
                raise RuntimeError("database engine is not initialized")
            with database.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception as exc:
            raise HTTPException(status_code=503, detail="service unavailable") from exc
        return {"status": "ready"}

    return application


app = create_application()
