"""R1 regression: real handler paths must distinguish zero, absence and bad input."""

import json
from datetime import datetime, timezone

import pytest
import respx

from percival_weather_mcp import series
from percival_weather_mcp.errors import InvalidRequestError, NoDataError
from percival_weather_mcp.presentation import WeatherFormatter
from percival_weather_mcp.tools.tools_air_quality import (
    GetAirQualityDetailsToolHandler,
    GetAirQualityToolHandler,
    _normalize_aq_variables,
)
from percival_weather_mcp.tools.tools_weather import (
    GetCurrentWeatherToolHandler,
    GetWeatherByDateRangeToolHandler,
    GetWeatherDetailsToolHandler,
)

REFERENCE = datetime(2026, 11, 5, 21, 20, tzinfo=timezone.utc)
GEO = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER = "https://api.open-meteo.com/v1/forecast"
AQ = "https://air-quality-api.open-meteo.com/v1/air-quality"


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(series, "utc_now", lambda: REFERENCE)


@pytest.mark.parametrize(
    "code,description",
    [(0, "Clear sky"), (None, "Weather condition unavailable"), (999, "Unknown weather condition")],
)
async def test_wmo_code_survives_current_forecast_and_range(code, description):
    with respx.mock as mock:
        mock.get(GEO).respond(200, json={"results": [{"latitude": 1, "longitude": 2}]})
        mock.get(WEATHER).respond(
            200,
            json={
                "hourly": {
                    "time": ["2026-11-05T21:00", "2026-11-05T22:00"],
                    "weather_code": [code, code],
                    "temperature_2m": [0, 0],
                    "pressure_msl": [None, 0],
                    "cloud_cover": [None, 0],
                }
            },
        )
        current = (await GetCurrentWeatherToolHandler().run_tool({"city": "Test"}))[0].text
        details = json.loads(
            (
                await GetWeatherDetailsToolHandler().run_tool(
                    {"city": "Test", "include_forecast": True}
                )
            )[0].text
        )
        by_range = json.loads(
            (
                await GetWeatherByDateRangeToolHandler().run_tool(
                    {
                        "city": "Test",
                        "start_date": "2026-11-05",
                        "end_date": "2026-11-05",
                    }
                )
            )[0].text
        )
    assert description in current
    assert (
        details["weather_description"]
        == details["forecast"][0]["weather_description"]
        == description
    )
    assert all(r["weather_description"] == description for r in by_range["hourly_sample"])
    assert details["temperature_c"] == 0
    assert "pressure is unavailable" in current and "unavailable% cloud" in current
    assert details["valid_time"] == "2026-11-05T21:00:00+00:00"
    assert details["valid_time"] in current
    assert "from the unavailable" in current  # A missing direction is not north.


def test_formatter_preserves_zero_and_reports_missing_time():
    text = WeatherFormatter().format_current(
        {
            "city": "Test",
            "temperature_c": 0,
            "wind_direction_degrees": 0,
            "pressure_hpa": 0,
            "cloud_cover_percent": 0,
        }
    )
    assert "0°C" in text and "from the N" in text
    assert "0 hPa" in text and "0% cloud" in text
    assert "Model valid time unavailable" in text


@pytest.mark.parametrize("handler", [GetAirQualityToolHandler, GetAirQualityDetailsToolHandler])
async def test_empty_variables_rejected_before_any_io(handler):
    with respx.mock(assert_all_called=False) as mock:
        with pytest.raises(InvalidRequestError, match=r"variables.*at least 1"):
            await handler().run_tool({"city": "Paris", "variables": []})
        assert not mock.calls
    with pytest.raises(InvalidRequestError, match="at least 1"):
        _normalize_aq_variables([], ["pm10"])
    assert _normalize_aq_variables(None, ["pm10"]) == ["pm10"]
    assert _normalize_aq_variables(["pm10", "pm10", "ozone"], []) == ["pm10", "ozone"]


@pytest.mark.parametrize(
    "city,rule",
    [("", "at least 1"), ("   ", "empty"), ("x" * 201, "200"), ("New<York>", "unsupported")],
)
async def test_city_rules_are_actionable_without_echoing_input(city, rule):
    with respx.mock(assert_all_called=False) as mock:
        with pytest.raises(InvalidRequestError) as info:
            await GetCurrentWeatherToolHandler().run_tool({"city": city})
        assert not mock.calls
    text = str(info.value)
    assert "city" in text and rule in text
    assert "input_value" not in text and "New<York>" not in text


@pytest.mark.parametrize("handler", [GetAirQualityToolHandler, GetAirQualityDetailsToolHandler])
@pytest.mark.parametrize("values,has_data", [([None, None], False), ([None, 0], True)])
async def test_all_null_pollutants_are_no_data_but_zero_is_valid(handler, values, has_data):
    with respx.mock as mock:
        mock.get(GEO).respond(200, json={"results": [{"latitude": 1, "longitude": 2}]})
        mock.get(AQ).respond(
            200, json={"hourly": {"time": ["2026-11-05T21:00", "2026-11-05T22:00"], "pm10": values}}
        )
        if not has_data:
            with pytest.raises(NoDataError, match="no valid numeric data"):
                await handler().run_tool({"city": "Test", "variables": ["pm10"]})
        else:
            data = json.loads(
                (await handler().run_tool({"city": "Test", "variables": ["pm10"]}))[0].text
            )
            assert data["coverage"]["variables"]["pm10"]["valid_points"] == 1
            assert data["coverage"]["variables"]["pm10"]["missing_points"] == 1


async def test_unexpected_value_error_does_not_echo_internal_details(monkeypatch):
    handler = GetCurrentWeatherToolHandler()

    async def broken(*args, **kwargs):
        raise ValueError("private-internal-value")

    monkeypatch.setattr(handler.weather_service, "get_current_weather", broken)
    with pytest.raises(InvalidRequestError) as info:
        await handler.run_tool({"city": "Test"})
    assert "private-internal-value" not in str(info.value)
