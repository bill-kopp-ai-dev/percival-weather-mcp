"""Formatting helpers for weather responses."""

from __future__ import annotations

from typing import Any

from .. import utils
from ..series import is_number

_COMPASS = [
    "N",
    "NNE",
    "NE",
    "ENE",
    "E",
    "ESE",
    "SE",
    "SSE",
    "S",
    "SSW",
    "SW",
    "WSW",
    "W",
    "WNW",
    "NW",
    "NNW",
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
        unknown = "unavailable"

        def _present(key: str) -> Any:
            value = weather_data.get(key)
            return value if is_number(value) else None

        temp = _present("temperature_c")
        feels_like = _present("apparent_temperature_c")
        if temp is None:
            temp_text = f"temperature {unknown}"
        else:
            temp_text = f"temperature of {temp}°C"
            if feels_like is not None and abs(feels_like - temp) > 2:
                temp_text += f" (feels like {feels_like}°C)"

        direction = _present("wind_direction_degrees")
        wind_dir = self.degrees_to_compass(direction) if direction is not None else unknown

        safe_city = utils.safe_inline_text(weather_data.get("city", "Unknown city"))
        location = weather_data.get("location") or {}
        context = ", ".join(
            utils.safe_inline_text(location[k])
            for k in ("name", "admin1", "country")
            if location.get(k)
        )
        if context:
            safe_city += f" ({context})"
        humidity = _present("relative_humidity_percent")
        dew_point = _present("dew_point_c")
        wind_speed = _present("wind_speed_kmh")
        wind_gusts = _present("wind_gusts_kmh")
        weather_description = weather_data.get("weather_description") or unknown

        text = (
            f"The weather in {safe_city} is {weather_description} "
            f"with a {temp_text}, "
            f"relative humidity at {humidity if humidity is not None else unknown}%, "
            f"and dew point at {dew_point if dew_point is not None else unknown}°C. "
            f"Wind is blowing from the {wind_dir} "
            f"at {wind_speed if wind_speed is not None else unknown} km/h "
            f"with gusts up to {wind_gusts if wind_gusts is not None else unknown} km/h."
        )

        precip_mm = _present("precipitation_mm") or 0.0
        rain_mm = _present("rain_mm") or 0.0
        snow_cm = _present("snowfall_cm") or 0.0
        precip_prob = _present("precipitation_probability_percent") or 0

        if precip_mm > 0 or precip_prob > 20:
            if snow_cm > 0:
                text += f" Snowfall of {snow_cm} cm is occurring."
            elif rain_mm > 0:
                text += f" Rainfall of {rain_mm} mm is occurring."

            if precip_prob > 0:
                text += f" Precipitation probability is {precip_prob}%."

        pressure = _present("pressure_hpa")
        clouds = _present("cloud_cover_percent")
        text += f" Atmospheric pressure is {pressure if pressure is not None else unknown} hPa with {clouds if clouds is not None else unknown}% cloud cover."

        uv = _present("uv_index")
        if uv is not None and uv > 3:
            text += f" UV index is {uv:.1f} ({self.uv_warning(uv)})."

        visibility = _present("visibility_m")
        if visibility is not None and visibility > 0:
            text += f" Visibility is {visibility / 1000:.1f} km."

        valid_time = weather_data.get("valid_time") or weather_data.get("time")
        text += (
            f" Model data valid at {utils.safe_inline_text(valid_time)} UTC (nearest_hour)."
            if valid_time
            else " Model valid time unavailable."
        )
        resolution = weather_data.get("resolution") or {}
        if resolution.get("ambiguous"):
            alternatives = [
                ", ".join(str(c.get(k)) for k in ("name", "admin1", "country") if c.get(k))
                for c in resolution.get("alternatives", [])
            ]
            text += (
                " Multiple location candidates; selected first provider candidate. Alternatives: "
                + utils.safe_inline_text("; ".join(alternatives), max_length=400)
                + "."
            )
        return text

    @staticmethod
    def format_range(weather_data: dict[str, Any]) -> str:
        """Format a date-range weather payload (delegates to utils)."""
        return utils.format_get_weather_bytime(weather_data)
