"""Weather-provider adapters selected at the composition root."""

from .factory import create_weather_provider

__all__ = ["create_weather_provider"]
