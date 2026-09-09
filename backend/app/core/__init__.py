"""Shared platform primitives with no dependency on GeoVision domains.

Domain, sector, integration, and worker packages may depend on ``app.core``.
The core package must never import those higher-level packages.
"""

# Keep package import side-effect free. Import concrete primitives from their
# modules, for example ``from app.core.config import settings``.

__all__: list[str] = []
