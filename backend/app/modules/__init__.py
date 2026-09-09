"""Common GeoVision domain modules.

Concrete legacy implementations remain under ``app.routers``, ``app.services``,
and ``app.models`` until their owning phases migrate them behind public domain
services. The registry is the authoritative composition boundary meanwhile.
"""

from .registry import DOMAIN_MODULES, DOMAIN_MODULES_BY_NAME

__all__ = ["DOMAIN_MODULES", "DOMAIN_MODULES_BY_NAME"]
