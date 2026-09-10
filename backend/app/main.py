# backend/app/main.py

from contextlib import asynccontextmanager

import logging
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .bootstrap import register_application_routes
from .core import database
from .core.config import settings
from .core.observability import configure_observability, get_logger, log_event
from .core.readiness import assert_database_ready
from .middleware import (
    HTTPSRedirectMiddleware,
    RateLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from .startup_bootstrap import run_compatibility_bootstrap
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

    if settings.startup_compatibility_bootstrap:
        run_compatibility_bootstrap()
    else:
        log_event(
            logger,
            logging.INFO,
            "application.compatibility_bootstrap.skipped",
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
            assert_database_ready(
                database.engine,
                require_current_schema=settings.readiness_require_current_schema,
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail="service unavailable") from exc
        return {"status": "ready"}

    return application


app = create_application()
