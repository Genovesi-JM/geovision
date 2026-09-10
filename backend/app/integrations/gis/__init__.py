"""GIS adapters selected at the application composition boundary."""

from .factory import create_gis_provider
from .miteco import MitecoOgcFeaturesProvider

__all__ = ["MitecoOgcFeaturesProvider", "create_gis_provider"]
