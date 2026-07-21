"""Regression tests pinning the tool input/output contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from percival_weather_mcp.models import (
    ConvertTimeInput,
    GetAirQualityDetailsInput,
    GetAirQualityInput,
    GetCurrentDateTimeInput,
    GetCurrentWeatherInput,
    GetTimeZoneInfoInput,
    GetWeatherByDateRangeInput,
    GetWeatherDetailsInput,
)
from percival_weather_mcp.tools.tools_air_quality import (
    _normalize_aq_variables,
)
from percival_weather_mcp.tools.tools_weather import (
    GetCurrentWeatherToolHandler,
    GetWeatherByDateRangeToolHandler,
    GetWeatherDetailsToolHandler,
)


@pytest.mark.parametrize(
    "model_cls,valid",
    [
        (GetCurrentWeatherInput, {"city": "London"}),
        (GetWeatherByDateRangeInput, {"city": "London", "start_date": "2026-01-01", "end_date": "2026-01-02"}),
        (GetWeatherDetailsInput, {"city": "London"}),
        (GetCurrentDateTimeInput, {"timezone_name": "UTC"}),
        (GetTimeZoneInfoInput, {"timezone_name": "UTC"}),
        (ConvertTimeInput, {"datetime_str": "now", "from_timezone": "UTC", "to_timezone": "America/Sao_Paulo"}),
        (GetAirQualityInput, {"city": "London"}),
        (GetAirQualityDetailsInput, {"city": "London"}),
    ],
)
def test_models_accept_valid_payload(model_cls, valid):
    instance = model_cls.model_validate(valid)
    for key, value in valid.items():
        assert getattr(instance, key) == value


@pytest.mark.parametrize(
    "model_cls,invalid",
    [
        (GetCurrentWeatherInput, {}),
        (GetCurrentDateTimeInput, {"timezone_name": ""}),
        (ConvertTimeInput, {"datetime_str": "now"}),
        (GetAirQualityInput, {"city": "London", "variables": ["invalid_pollutant"]}),
    ],
)
def test_models_reject_invalid_payload(model_cls, invalid):
    with pytest.raises(ValidationError):
        model_cls.model_validate(invalid)


def test_normalize_aq_variables_defaults():
    defaults = ["pm10", "pm2_5"]
    assert _normalize_aq_variables(None, defaults) == defaults


def test_normalize_aq_variables_rejects_unknown():
    with pytest.raises(ValueError):
        _normalize_aq_variables(["unknown"], ["pm2_5"])


def test_tool_handlers_expose_valid_schemas():
    for handler_cls in (
        GetCurrentWeatherToolHandler,
        GetWeatherByDateRangeToolHandler,
        GetWeatherDetailsToolHandler,
    ):
        handler = handler_cls()
        schema = handler.get_tool_description()
        assert schema.name == handler.name
        assert "properties" in schema.inputSchema
        assert "city" in schema.inputSchema["properties"]
