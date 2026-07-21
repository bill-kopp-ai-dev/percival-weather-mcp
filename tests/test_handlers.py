"""Tests for the tool registration + handler integration."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from percival_weather_mcp import server
from percival_weather_mcp.models import (
    EXTENDED_AIR_QUALITY_VARIABLES,
    GetCurrentWeatherInput,
)
from percival_weather_mcp.tools.toolhandler import ToolHandler


@pytest.fixture(autouse=True)
def _reset_handlers():
    server.tool_handlers.clear()
    yield
    server.tool_handlers.clear()


def test_register_all_tools_registers_every_tool():
    server.register_all_tools()
    expected = {
        "weather_get_current",
        "weather_get_by_range",
        "weather_get_details",
        "weather_get_time",
        "weather_get_timezone",
        "weather_convert_time",
        "weather_get_air_quality",
        "weather_get_air_quality_details",
    }
    assert expected.issubset(set(server.tool_handlers.keys()))


def test_resolve_tool_name_legacy_alias():
    assert server.resolve_tool_name("get_current_weather") == "weather_get_current"
    assert server.resolve_tool_name("weather_get_current") == "weather_get_current"


def test_tool_handlers_are_subclasses_of_basetool():
    server.register_all_tools()
    for handler in server.tool_handlers.values():
        assert isinstance(handler, ToolHandler)


def test_input_model_validates_city_field():
    parsed = GetCurrentWeatherInput(city="São Paulo")
    assert parsed.city == "São Paulo"
    with pytest.raises(ValidationError):
        GetCurrentWeatherInput()


def test_extended_air_quality_variables_covers_all_supported():
    assert "pm2_5" in EXTENDED_AIR_QUALITY_VARIABLES
    assert "ozone" in EXTENDED_AIR_QUALITY_VARIABLES


def test_get_tool_handler_returns_registered():
    server.register_all_tools()
    handler = server.get_tool_handler("weather_get_current")
    assert handler is not None
    assert handler.name == "weather_get_current"
