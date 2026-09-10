"""GIS adapters selected at the application composition boundary."""

from .factory import create_gis_provider

__all__ = ["create_gis_provider"]
