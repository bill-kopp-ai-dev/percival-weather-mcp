"""Presentation layer: format domain data into agent-friendly text or JSON.

This package isolates formatting helpers from the service layer so they can be
unit tested independently and reused across multiple tool handlers.
"""

from .air_quality_formatter import AirQualityFormatter
from .weather_formatter import WeatherFormatter

__all__ = ["AirQualityFormatter", "WeatherFormatter"]
