"""Formatting helpers for weather responses."""

from __future__ import annotations

from typing import Any

from .. import utils

_COMPASS = [
    "N", "NNE", "NE", "ENE",
    "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW",
    "W", "WNW", "NW", "NNW",
]


class WeatherFormatter:
    """Stateless helpers that turn raw weather payloads into readable text."""

    @staticmethod
    def degrees_to_compass(degrees: float) -> str:
        """Convert wind direction in degrees to a 16-point compass label."""
        return _COMPASS[round(degrees / 22.5) % 16]

    @staticmethod
    def uv_warning(uv_index: float) -> str:
        """Return the WHO-style UV warning label."""
        if uv_index < 3:
            return "Low"
        if uv_index < 6:
            return "Moderate"
        if uv_index < 8:
            return "High"
        if uv_index < 11:
            return "Very High"
        return "Extreme"

    def format_current(self, weather_data: dict[str, Any]) -> str:
        temp = weather_data["temperature_c"]
        feels_like = weather_data.get("apparent_temperature_c", temp)

        temp_text = f"temperature of {temp}°C"
        if abs(feels_like - temp) > 2:
            temp_text += f" (feels like {feels_like}°C)"

        wind_dir = self.degrees_to_compass(weather_data.get("wind_direction_degrees", 0))

        safe_city = utils.safe_inline_text(weather_data.get("city", "Unknown city"))
        text = (
            f"The weather in {safe_city} is {weather_data['weather_description']} "
            f"with a {temp_text}, "
            f"relative humidity at {weather_data['relative_humidity_percent']}%, "
            f"and dew point at {weather_data['dew_point_c']}°C. "
            f"Wind is blowing from the {wind_dir} at {weather_data['wind_speed_kmh']} km/h "
            f"with gusts up to {weather_data['wind_gusts_kmh']} km/h."
        )

        precip_mm = weather_data.get("precipitation_mm", 0)
        rain_mm = weather_data.get("rain_mm", 0)
        snow_cm = weather_data.get("snowfall_cm", 0)
        precip_prob = weather_data.get("precipitation_probability_percent", 0)

        if precip_mm > 0 or precip_prob > 20:
            if snow_cm > 0:
                text += f" Snowfall of {snow_cm} cm is occurring."
            elif rain_mm > 0:
                text += f" Rainfall of {rain_mm} mm is occurring."

            if precip_prob > 0:
                text += f" Precipitation probability is {precip_prob}%."

        pressure = weather_data.get("pressure_hpa", 0)
        clouds = weather_data.get("cloud_cover_percent", 0)
        text += f" Atmospheric pressure is {pressure} hPa with {clouds}% cloud cover."

        uv = weather_data.get("uv_index", 0)
        if uv > 3:
            text += f" UV index is {uv:.1f} ({self.uv_warning(uv)})."

        visibility = weather_data.get("visibility_m", 0)
        if visibility > 0:
            text += f" Visibility is {visibility / 1000:.1f} km."

        return text

    @staticmethod
    def format_range(weather_data: dict[str, Any]) -> str:
        """Format a date-range weather payload (delegates to utils)."""
        return utils.format_get_weather_bytime(weather_data)
