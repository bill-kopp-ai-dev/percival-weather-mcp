"""Regression tests for the presentation layer handling of ``None`` fields.

The Open-Meteo hourly series can return ``null`` for fields the upstream
omits for a given timestamp. The formatters used to embed ``"None"`` in
the rendered prose ("temperature of None°C"), which is not useful to the
agent and never occurred before the 0.7 -> 0.8 schema change.

These tests pin the expected "missing data" rendering so future changes
keep the formatter robust.
"""

from __future__ import annotations

from percival_weather_mcp.presentation import WeatherFormatter


def _payload(**overrides):
    base = {
        "city": "London",
        "temperature_c": 10,
        "apparent_temperature_c": 10,
        "relative_humidity_percent": 80,
        "dew_point_c": 7,
        "weather_description": "Clear sky",
        "wind_speed_kmh": 12,
        "wind_direction_degrees": 90,
        "wind_gusts_kmh": 18,
        "precipitation_mm": 0.0,
        "rain_mm": 0.0,
        "snowfall_cm": 0.0,
        "precipitation_probability_percent": 0,
        "pressure_hpa": 1015,
        "cloud_cover_percent": 90,
        "uv_index": 1.5,
        "visibility_m": 9000,
    }
    base.update(overrides)
    return base


def test_format_current_renders_missing_temperature_as_unavailable():
    out = WeatherFormatter().format_current(_payload(temperature_c=None))
    assert "None" not in out
    assert "unavailable" in out.lower()


def test_format_current_renders_missing_humidity_as_unavailable():
    out = WeatherFormatter().format_current(_payload(relative_humidity_percent=None))
    assert "None" not in out


def test_format_current_renders_missing_wind_as_unavailable():
    out = WeatherFormatter().format_current(_payload(wind_speed_kmh=None, wind_gusts_kmh=None))
    assert "None" not in out


def test_format_current_omits_uv_section_when_index_missing():
    out = WeatherFormatter().format_current(_payload(uv_index=None))
    assert "UV index" not in out
    assert "None" not in out


def test_format_current_omits_visibility_section_when_missing():
    out = WeatherFormatter().format_current(_payload(visibility_m=None))
    assert "Visibility" not in out
    assert "None" not in out
