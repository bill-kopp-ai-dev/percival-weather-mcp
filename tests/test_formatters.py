"""Tests for presentation-layer formatters."""

from __future__ import annotations

import json

from percival_weather_mcp.presentation import AirQualityFormatter, WeatherFormatter


def _weather_payload(**overrides):
    base = {
        "city": "London",
        "temperature_c": 10,
        "apparent_temperature_c": 8,
        "relative_humidity_percent": 80,
        "dew_point_c": 7,
        "weather_description": "Light rain",
        "wind_speed_kmh": 12,
        "wind_direction_degrees": 90,
        "wind_gusts_kmh": 18,
        "precipitation_mm": 0.5,
        "rain_mm": 0.4,
        "snowfall_cm": 0,
        "precipitation_probability_percent": 60,
        "pressure_hpa": 1015,
        "cloud_cover_percent": 90,
        "uv_index": 1.5,
        "visibility_m": 9000,
    }
    base.update(overrides)
    return base


def test_weather_formatter_basic():
    out = WeatherFormatter().format_current(_weather_payload(apparent_temperature_c=6))
    assert "London" in out
    assert "Light rain" in out
    assert "10°C" in out
    assert "feels like 6°C" in out


def test_weather_formatter_no_feels_like_when_close():
    out = WeatherFormatter().format_current(_weather_payload(apparent_temperature_c=12))
    assert "feels like" not in out


def test_weather_formatter_snow_branch():
    out = WeatherFormatter().format_current(
        _weather_payload(snowfall_cm=2.0, rain_mm=0, precipitation_mm=2.0)
    )
    assert "Snowfall of 2.0 cm" in out


def test_weather_formatter_compass_points():
    assert WeatherFormatter.degrees_to_compass(0) == "N"
    assert WeatherFormatter.degrees_to_compass(90) == "E"
    assert WeatherFormatter.degrees_to_compass(180) == "S"
    assert WeatherFormatter.degrees_to_compass(270) == "W"
    assert WeatherFormatter.degrees_to_compass(360) == "N"


def test_uv_warning_buckets():
    f = WeatherFormatter()
    assert f.uv_warning(1) == "Low"
    assert f.uv_warning(4) == "Moderate"
    assert f.uv_warning(7) == "High"
    assert f.uv_warning(10) == "Very High"
    assert f.uv_warning(15) == "Extreme"


def test_air_quality_legacy_format_includes_pollutants():
    aq = {"pm2_5": 5, "pm10": 10, "ozone": 30}
    out = AirQualityFormatter().format_legacy("Paris", 48.85, 2.35, aq)
    assert "PM2.5" in out
    assert "Good" in out
    assert "PM10" in out
    assert "Ozone" in out


def test_air_quality_comprehensive_is_valid_json():
    response_data = {
        "city": "Paris",
        "latitude": 48.85,
        "longitude": 2.35,
        "current_air_quality": {"pm2_5": 5, "time": "2026-01-01T00:00"},
        "full_data": {
            "hourly": {
                "time": ["2026-01-01T00:00", "2026-01-01T01:00"],
                "pm2_5": [5, 6],
                "pm10": [10, 11],
            }
        },
    }
    payload = json.loads(AirQualityFormatter.format_comprehensive(response_data))
    assert payload["city"] == "Paris"
    assert payload["summary"]["pollutants"]["pm2_5"]["max"] == 6
    assert len(payload["hourly_sample"]) == 2
