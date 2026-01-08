"""GeoVision FastAPI application package.

This file exposes the FastAPI `app` so tools like uvicorn can import
the application via `app.main:app` or `app:app` when the package is used.
"""
"""Package initializer for the `app` package.

We intentionally avoid importing `app.main` (and thus avoid creating the
FastAPI app at package import time) because tests and tooling may set
configuration (like the database URL) before creating the application.

Import `create_application` from `app.main` when you need to construct the
app (for example in entrypoints or tests).
"""

__all__ = []
