"""Static knowledge tables exposed via MCP resources.

These tables help the agent interpret raw data returned by the weather/air
quality APIs without having to memorise the WMO code list or the WHO/EPA
pollutant thresholds.

* :func:`weather_code_table` — WMO weather codes 0-99 with descriptions.
* :func:`aqi_table` — air-quality risk bands per pollutant.
* :func:`timezone_table` — curated list of common IANA timezones.
"""

from __future__ import annotations


def weather_code_table() -> list[dict[str, object]]:
    """Return the WMO weather code reference table.

    Sources: Open-Meteo / WMO Code Table 4677. The list is intentionally
    limited to the codes used by the Open-Meteo API.
    """
    return [
        {"code": 0, "description": "Clear sky"},
        {"code": 1, "description": "Mainly clear"},
        {"code": 2, "description": "Partly cloudy"},
        {"code": 3, "description": "Overcast"},
        {"code": 45, "description": "Fog"},
        {"code": 48, "description": "Depositing rime fog"},
        {"code": 51, "description": "Drizzle: light intensity"},
        {"code": 53, "description": "Drizzle: moderate intensity"},
        {"code": 55, "description": "Drizzle: dense intensity"},
        {"code": 56, "description": "Freezing drizzle: light"},
        {"code": 57, "description": "Freezing drizzle: dense"},
        {"code": 61, "description": "Rain: slight intensity"},
        {"code": 63, "description": "Rain: moderate intensity"},
        {"code": 65, "description": "Rain: heavy intensity"},
        {"code": 66, "description": "Freezing rain: light"},
        {"code": 67, "description": "Freezing rain: heavy"},
        {"code": 71, "description": "Snowfall: slight"},
        {"code": 73, "description": "Snowfall: moderate"},
        {"code": 75, "description": "Snowfall: heavy"},
        {"code": 77, "description": "Snow grains"},
        {"code": 80, "description": "Rain showers: slight"},
        {"code": 81, "description": "Rain showers: moderate"},
        {"code": 82, "description": "Rain showers: violent"},
        {"code": 85, "description": "Snow showers: slight"},
        {"code": 86, "description": "Snow showers: heavy"},
        {"code": 95, "description": "Thunderstorm: slight or moderate"},
        {"code": 96, "description": "Thunderstorm with slight hail"},
        {"code": 99, "description": "Thunderstorm with heavy hail"},
    ]


def aqi_table() -> dict[str, list[dict[str, object]]]:
    """Return air-quality risk bands per pollutant.

    Bands follow the WHO 2021 guidelines (PM2.5/PM10) and the EPA AQI
    breakpoints (O3/NO2/SO2/CO). Each entry includes the lower bound,
    the upper bound (inclusive) and a human-readable label.
    """
    return {
        "pm2_5": [
            {
                "min": 0,
                "max": 12,
                "label": "Good",
                "advice": "Air quality is good. Safe for outdoor activities.",
            },
            {
                "min": 12.1,
                "max": 35.4,
                "label": "Moderate",
                "advice": "Acceptable; sensitive groups should monitor symptoms.",
            },
            {
                "min": 35.5,
                "max": 55.4,
                "label": "Unhealthy for Sensitive Groups",
                "advice": "Sensitive groups should limit prolonged outdoor exertion.",
            },
            {
                "min": 55.5,
                "max": 150.4,
                "label": "Unhealthy",
                "advice": "Everyone should reduce outdoor activity; sensitive groups should stay indoors.",
            },
            {
                "min": 150.5,
                "max": 250.4,
                "label": "Very Unhealthy",
                "advice": "Everyone should avoid outdoor exertion; sensitive groups remain indoors.",
            },
            {
                "min": 250.5,
                "max": 500.4,
                "label": "Hazardous",
                "advice": "Health alert: avoid all outdoor activity.",
            },
        ],
        "pm10": [
            {"min": 0, "max": 54, "label": "Good"},
            {"min": 55, "max": 154, "label": "Moderate"},
            {"min": 155, "max": 254, "label": "Unhealthy for Sensitive Groups"},
            {"min": 255, "max": 354, "label": "Unhealthy"},
            {"min": 355, "max": 424, "label": "Very Unhealthy"},
            {"min": 425, "max": 604, "label": "Hazardous"},
        ],
        "ozone": [
            {"min": 0, "max": 54, "label": "Good"},
            {"min": 55, "max": 70, "label": "Moderate"},
            {"min": 71, "max": 85, "label": "Unhealthy for Sensitive Groups"},
            {"min": 86, "max": 105, "label": "Unhealthy"},
            {"min": 106, "max": 200, "label": "Very Unhealthy"},
        ],
        "nitrogen_dioxide": [
            {"min": 0, "max": 53, "label": "Good"},
            {"min": 54, "max": 100, "label": "Moderate"},
            {"min": 101, "max": 360, "label": "Unhealthy for Sensitive Groups"},
            {"min": 361, "max": 649, "label": "Unhealthy"},
            {"min": 650, "max": 1249, "label": "Very Unhealthy"},
            {"min": 1250, "max": 2049, "label": "Hazardous"},
        ],
        "sulphur_dioxide": [
            {"min": 0, "max": 35, "label": "Good"},
            {"min": 36, "max": 75, "label": "Moderate"},
            {"min": 76, "max": 185, "label": "Unhealthy for Sensitive Groups"},
            {"min": 186, "max": 304, "label": "Unhealthy"},
            {"min": 305, "max": 604, "label": "Very Unhealthy"},
            {"min": 605, "max": 1004, "label": "Hazardous"},
        ],
        "carbon_monoxide": [
            {"min": 0, "max": 4400, "label": "Good"},
            {"min": 4401, "max": 9400, "label": "Moderate"},
            {"min": 9401, "max": 12400, "label": "Unhealthy for Sensitive Groups"},
            {"min": 12401, "max": 15400, "label": "Unhealthy"},
            {"min": 15401, "max": 30400, "label": "Very Unhealthy"},
            {"min": 30401, "max": 50400, "label": "Hazardous"},
        ],
    }


def timezone_table() -> list[dict[str, str]]:
    """Return a curated list of commonly-used IANA timezones.

    This is NOT the full IANA database — only the timezones most agents
    encounter. For full coverage refer to the IANA tz database at
    https://www.iana.org/time-zones.
    """
    return [
        {"iana": "UTC", "display": "Coordinated Universal Time", "offset": "+00:00"},
        {"iana": "Africa/Cairo", "display": "Egypt", "offset": "+02:00"},
        {"iana": "Africa/Johannesburg", "display": "South Africa", "offset": "+02:00"},
        {"iana": "Africa/Lagos", "display": "West Africa", "offset": "+01:00"},
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
    """Return schema descriptions for the detailed tool outputs.

    Helps the agent know which top-level keys to expect before calling
    ``weather_get_details`` / ``weather_get_by_range`` /
    ``weather_get_air_quality_details``.
    """
    return {
        "weather_get_details": {
            "top_level_keys": [
                "city",
                "latitude",
                "longitude",
                "time",
                "temperature_c",
                "relative_humidity_percent",
                "dew_point_c",
                "weather_code",
                "weather_description",
                "wind_speed_kmh",
                "wind_direction_degrees",
                "wind_gusts_kmh",
                "precipitation_mm",
                "rain_mm",
                "snowfall_cm",
                "precipitation_probability_percent",
                "pressure_hpa",
                "cloud_cover_percent",
                "uv_index",
                "apparent_temperature_c",
                "visibility_m",
                "forecast (only when include_forecast=true)",
            ],
            "notes": "All values are nullable when the upstream API returns no data for that timestamp.",
        },
        "weather_get_by_range": {
            "top_level_keys": [
                "city",
                "latitude",
                "longitude",
                "start_date",
                "end_date",
                "summary (avg/min/max temperature, total precipitation, ...)",
                "hourly_sample (compact hourly observations, capped to a few hundred entries)",
            ],
            "notes": "The range is inclusive and capped at 16 days. Dates outside this window raise a ValueError.",
        },
        "weather_get_air_quality_details": {
            "top_level_keys": [
                "city",
                "latitude",
                "longitude",
                "current_air_quality (closest hour to now)",
                "full_data.hourly (complete hourly series from Open-Meteo)",
            ],
            "notes": "Use weather_get_air_quality when you only need the summary; use the _details variant when you must compute statistics yourself.",
        },
    }
