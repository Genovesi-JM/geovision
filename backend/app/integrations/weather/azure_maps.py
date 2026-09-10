"""Azure Maps Weather scaffold kept behind the WeatherProvider boundary."""

from .unavailable import UnavailableWeatherProvider


class AzureMapsWeatherProvider(UnavailableWeatherProvider):
    def __init__(self) -> None:
        super().__init__(
            "azure_maps",
            "Azure Maps Weather is a documented future adapter and has no production calls",
        )
