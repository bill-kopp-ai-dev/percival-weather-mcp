"""Shared reference data and generated schemas exposed through MCP resources."""

from __future__ import annotations

from .air_quality_index import reference_payload
from .config import get_settings
from .output_models import AirQualityDetails, OutputModel, WeatherDetails, WeatherRange
from .utils import weather_descriptions


def weather_code_table() -> list[dict[str, object]]:
    """Open-Meteo WMO codes, from the same table as current/range responses."""
    return [{"code": code, "description": text} for code, text in weather_descriptions.items()]


def aqi_table() -> dict[str, list[dict[str, object]]]:
    """Compatibility accessor: dimensionless index bands, not mass concentrations."""
    return reference_payload()["bands"]


def timezone_table() -> list[dict[str, str]]:
    """Curated reference; use IANA ZoneInfo to calculate actual date-specific offsets."""
    return [
        {"iana": "UTC", "display": "Coordinated Universal Time", "offset": "+00:00"},
        {"iana": "Africa/Cairo", "display": "Egypt", "offset": "+02:00"},
        {"iana": "Africa/Johannesburg", "display": "South Africa", "offset": "+02:00"},
        {"iana": "Africa/Lagos", "display": "Nigeria", "offset": "+01:00"},
        {"iana": "America/Anchorage", "display": "Alaska", "offset": "-09:00/-08:00"},
        {"iana": "America/Argentina/Buenos_Aires", "display": "Argentina", "offset": "-03:00"},
        {"iana": "America/Bogota", "display": "Colombia", "offset": "-05:00"},
        {"iana": "America/Chicago", "display": "Central Time (US)", "offset": "-06:00/-05:00"},
        {"iana": "America/Denver", "display": "Mountain Time (US)", "offset": "-07:00/-06:00"},
        {"iana": "America/Halifax", "display": "Atlantic Time (Canada)", "offset": "-04:00/-03:00"},
        {"iana": "America/Los_Angeles", "display": "Pacific Time (US)", "offset": "-08:00/-07:00"},
        {"iana": "America/Mexico_City", "display": "Mexico (Central)", "offset": "-06:00"},
        {"iana": "America/New_York", "display": "Eastern Time (US)", "offset": "-05:00/-04:00"},
        {"iana": "America/Phoenix", "display": "Arizona", "offset": "-07:00"},
        {"iana": "America/Sao_Paulo", "display": "Brazil (Southeast)", "offset": "-03:00"},
        {"iana": "America/Toronto", "display": "Eastern Time (Canada)", "offset": "-05:00/-04:00"},
        {"iana": "Asia/Bangkok", "display": "Thailand", "offset": "+07:00"},
        {"iana": "Asia/Dubai", "display": "United Arab Emirates", "offset": "+04:00"},
        {"iana": "Asia/Hong_Kong", "display": "Hong Kong", "offset": "+08:00"},
        {"iana": "Asia/Jakarta", "display": "Indonesia (West)", "offset": "+07:00"},
        {"iana": "Asia/Karachi", "display": "Pakistan", "offset": "+05:00"},
        {"iana": "Asia/Kolkata", "display": "India", "offset": "+05:30"},
        {"iana": "Asia/Manila", "display": "Philippines", "offset": "+08:00"},
        {"iana": "Asia/Seoul", "display": "South Korea", "offset": "+09:00"},
        {"iana": "Asia/Shanghai", "display": "China", "offset": "+08:00"},
        {"iana": "Asia/Singapore", "display": "Singapore", "offset": "+08:00"},
        {"iana": "Asia/Taipei", "display": "Taiwan", "offset": "+08:00"},
        {"iana": "Asia/Tehran", "display": "Iran", "offset": "+03:30/+04:30"},
        {"iana": "Asia/Tokyo", "display": "Japan", "offset": "+09:00"},
        {"iana": "Australia/Melbourne", "display": "Australia (East)", "offset": "+10:00/+11:00"},
        {"iana": "Australia/Perth", "display": "Australia (West)", "offset": "+08:00"},
        {"iana": "Australia/Sydney", "display": "Australia (East)", "offset": "+10:00/+11:00"},
        {"iana": "Europe/Amsterdam", "display": "Netherlands", "offset": "+01:00/+02:00"},
        {"iana": "Europe/Berlin", "display": "Germany", "offset": "+01:00/+02:00"},
        {"iana": "Europe/Dublin", "display": "Ireland", "offset": "+00:00/+01:00"},
        {"iana": "Europe/Istanbul", "display": "Turkey", "offset": "+03:00"},
        {"iana": "Europe/London", "display": "United Kingdom", "offset": "+00:00/+01:00"},
        {"iana": "Europe/Madrid", "display": "Spain", "offset": "+01:00/+02:00"},
        {"iana": "Europe/Moscow", "display": "Russia (Moscow)", "offset": "+03:00"},
        {"iana": "Europe/Paris", "display": "France", "offset": "+01:00/+02:00"},
        {"iana": "Europe/Rome", "display": "Italy", "offset": "+01:00/+02:00"},
        {"iana": "Europe/Warsaw", "display": "Poland", "offset": "+01:00/+02:00"},
        {"iana": "Pacific/Auckland", "display": "New Zealand", "offset": "+12:00/+13:00"},
        {"iana": "Pacific/Honolulu", "display": "Hawaii", "offset": "-10:00"},
    ]


def tool_response_schemas() -> dict[str, dict[str, object]]:
    """Schemas generated from the very models used by response serialization."""
    models: dict[str, type[OutputModel]] = {
        "weather_get_details": WeatherDetails,
        "weather_get_by_range": WeatherRange,
        "weather_get_air_quality_details": AirQualityDetails,
    }
    notes = {
        "weather_get_details": "Nearest-hour model data, valid_time and reference_time in UTC. Forecast is optional.",
        "weather_get_by_range": f"Inclusive range, at most {get_settings().max_date_range_days} days; UTC today-92 through today+15. period holds dates; min/max/avg are over valid values of the entire returned window, not total precipitation. hourly_sample has at most 12 rows (first/last/spread). coverage splits past_or_present and future model data.",
        "weather_get_air_quality_details": "full_data preserves every returned upstream key and array; coverage and provider-computed US AQI subindices are metadata. No hidden truncation. Payload grows with hours times variables.",
    }
    return {
        name: {
            "top_level_keys": list(model.model_fields),
            "json_schema": model.model_json_schema(),
            "notes": notes[name],
        }
        for name, model in models.items()
    }
