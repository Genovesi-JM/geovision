"""Standard-library observability entry points for application modules."""

from __future__ import annotations

import logging


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger without configuring process-wide handlers."""

    if name.startswith("app."):
        return logging.getLogger(name)
    return logging.getLogger(f"app.{name}")


__all__ = ["get_logger"]
