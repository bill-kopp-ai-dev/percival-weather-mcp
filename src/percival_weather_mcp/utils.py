
import json
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from dateutil import parser
from mcp import McpError
from mcp.types import ErrorData
from pydantic import BaseModel


class TimeResult(BaseModel):
    timezone: str
    datetime: str


MAX_CITY_NAME_LENGTH = 120
MAX_TIMEZONE_NAME_LENGTH = 64
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")
_MULTISPACE_RE = re.compile(r"\s+")
_CITY_FORBIDDEN_CHARS_RE = re.compile(r"[<>{}\[\]`$|\\]")
_TIMEZONE_FORBIDDEN_CHARS_RE = re.compile(r"[^A-Za-z0-9/_+\-]")


def normalize_city_name(city: str) -> str:
    """
    Normalize and validate city names provided by users.

    The returned value is safe for logs, prompts, and outbound API requests.
    """
    if not isinstance(city, str):
        raise ValueError("City must be a string.")

    normalized = _CONTROL_CHARS_RE.sub("", city)
    normalized = _MULTISPACE_RE.sub(" ", normalized).strip()

    if not normalized:
        raise ValueError("City must not be empty.")

    if len(normalized) > MAX_CITY_NAME_LENGTH:
        raise ValueError(f"City must be at most {MAX_CITY_NAME_LENGTH} characters.")

    if _CITY_FORBIDDEN_CHARS_RE.search(normalized):
        raise ValueError("City contains unsupported characters.")

    return normalized


def safe_inline_text(value: str, *, max_length: int = 140) -> str:
    """Sanitize untrusted text for compact inline responses."""
    normalized = _CONTROL_CHARS_RE.sub("", str(value))
    normalized = _MULTISPACE_RE.sub(" ", normalized).strip()
    if len(normalized) > max_length:
        return normalized[:max_length].rstrip() + "..."
    return normalized


def get_zoneinfo(timezone_name: str) -> ZoneInfo:
    if not isinstance(timezone_name, str):
        error_data = ErrorData(code=-1, message="Invalid timezone")
        raise McpError(error_data)

    cleaned = _CONTROL_CHARS_RE.sub("", timezone_name).strip()
    if not cleaned:
        error_data = ErrorData(code=-1, message="Invalid timezone")
        raise McpError(error_data)
    if len(cleaned) > MAX_TIMEZONE_NAME_LENGTH:
        error_data = ErrorData(code=-1, message="Invalid timezone")
        raise McpError(error_data)
    if _TIMEZONE_FORBIDDEN_CHARS_RE.search(cleaned):
        error_data = ErrorData(code=-1, message="Invalid timezone")
        raise McpError(error_data)

    try:
        return ZoneInfo(cleaned)
    except Exception as err:
        error_data = ErrorData(code=-1, message="Invalid timezone")
        raise McpError(error_data) from err

def format_get_weather_bytime(data_result: Any) -> str:
    """
    Format weather data into a compact, agent-friendly payload.

    Args:
        data_result: Dictionary containing weather forecast data

    Returns:
        Formatted string with weather data and field explanations
    """
    weather_data = data_result.get("weather_data", []) or []

    def _numeric_series(key: str) -> list[float]:
        values: list[float] = []
        for row in weather_data:
            value = row.get(key)
            if isinstance(value, (int, float)):
                values.append(float(value))
        return values

    def _stats(values: list[float]) -> dict[str, float | None]:
        if not values:
            return {"min": None, "max": None, "avg": None}
        return {
            "min": round(min(values), 2),
            "max": round(max(values), 2),
            "avg": round(sum(values) / len(values), 2),
        }

    weather_counter = Counter(
        row.get("weather_description", "Unknown")
        for row in weather_data
        if row.get("weather_description")
    )

    payload = {
        "city": data_result.get("city"),
        "latitude": data_result.get("latitude"),
        "longitude": data_result.get("longitude"),
        "period": {
            "start_date": data_result.get("start_date"),
            "end_date": data_result.get("end_date"),
            "hourly_points": len(weather_data),
        },
        "summary": {
            "temperature_c": _stats(_numeric_series("temperature_c")),
            "apparent_temperature_c": _stats(_numeric_series("apparent_temperature_c")),
            "precipitation_mm": _stats(_numeric_series("precipitation_mm")),
            "wind_speed_kmh": _stats(_numeric_series("wind_speed_kmh")),
            "uv_index": _stats(_numeric_series("uv_index")),
            "top_conditions": weather_counter.most_common(3),
        },
        "hourly_sample": weather_data[:12],
    }
    return json.dumps(payload, indent=2)

def format_air_quality_data(data_result: Any) -> str:
    """
    Format air quality data into a compact, agent-friendly payload.

    Args:
        data_result: Dictionary containing air quality data

    Returns:
        Formatted string with air quality data and field explanations
    """
    full_data = data_result.get("full_data", {}) or {}
    hourly = full_data.get("hourly", {}) if isinstance(full_data, dict) else {}
    times = hourly.get("time", []) if isinstance(hourly.get("time", []), list) else []

    def _numeric_series(key: str) -> list[float]:
        raw_values = hourly.get(key, [])
        if not isinstance(raw_values, list):
            return []
        values: list[float] = []
        for value in raw_values:
            if isinstance(value, (int, float)):
                values.append(float(value))
        return values

    def _stats(values: list[float]) -> dict[str, float | None]:
        if not values:
            return {"min": None, "max": None, "avg": None}
        return {
            "min": round(min(values), 2),
            "max": round(max(values), 2),
            "avg": round(sum(values) / len(values), 2),
        }

    pollutants = [
        "pm2_5",
        "pm10",
        "ozone",
        "nitrogen_dioxide",
        "carbon_monoxide",
        "sulphur_dioxide",
        "ammonia",
        "dust",
        "aerosol_optical_depth",
    ]

    hourly_sample = []
    for i, timestamp in enumerate(times[:8]):
        row: dict[str, Any] = {"time": timestamp}
        for pollutant in pollutants:
            values = hourly.get(pollutant, [])
            if isinstance(values, list) and i < len(values):
                row[pollutant] = values[i]
        hourly_sample.append(row)

    payload = {
        "city": data_result.get("city"),
        "latitude": data_result.get("latitude"),
        "longitude": data_result.get("longitude"),
        "current_air_quality": data_result.get("current_air_quality"),
        "summary": {
            "hourly_points": len(times),
            "pollutants": {
                pollutant: _stats(_numeric_series(pollutant))
                for pollutant in pollutants
                if pollutant in hourly
            },
        },
        "hourly_sample": hourly_sample,
    }
    return json.dumps(payload, indent=2)

def get_closest_utc_index(hourly_times: list[str]) -> int:
    """
    Returns the index of the datetime in `hourly_times` closest to the current UTC time
    or a provided datetime.

    :param hourly_times: List of ISO 8601 time strings (UTC)
    :return: Index of the closest datetime in the list
    """

    current_time = datetime.now(timezone.utc)
    parsed_times = [
        parser.isoparse(t).replace(tzinfo=timezone.utc) if parser.isoparse(t).tzinfo is None
        else parser.isoparse(t).astimezone(timezone.utc)
        for t in hourly_times
    ]

    return min(range(len(parsed_times)), key=lambda i: abs(parsed_times[i] - current_time))

# Weather code descriptions (from Open-Meteo documentation)
weather_descriptions = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}
