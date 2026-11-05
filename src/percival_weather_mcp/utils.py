import re
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


MAX_CITY_NAME_LENGTH = 200
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
    """Compatibility adapter to the validated range formatter."""
    from .presentation.payloads import weather_range

    return weather_range(data_result)


def format_air_quality_data(data_result: Any) -> str:
    """Compatibility adapter to the validated air-quality formatter."""
    from .presentation.payloads import air_quality

    return air_quality(data_result)


def _parse_utc(timestamp: str) -> datetime:
    parsed = parser.isoparse(timestamp)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def get_closest_utc_index(hourly_times: list[str], *, reference: datetime | None = None) -> int:
    """
    Returns the index of the datetime in `hourly_times` closest to the current UTC time
    or a provided datetime.

    :param hourly_times: List of ISO 8601 time strings (UTC)
    :return: Index of the closest datetime in the list
    """

    from .series import utc_now

    current_time = reference or utc_now()
    parsed_times = [_parse_utc(t) for t in hourly_times]

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


def describe_weather(code: Any) -> str:
    if code is None:
        return "Weather condition unavailable"
    from .series import is_number

    if not is_number(code) or code != int(code):
        return "Unknown weather condition"
    return weather_descriptions.get(code, "Unknown weather condition")
