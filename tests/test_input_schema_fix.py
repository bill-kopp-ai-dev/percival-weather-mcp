"""Regression tests for the FastMCP input-schema bug.

See ``MCP_Docs/Issues/2026-07-21-percival-weather-mcp-broken-input-schema.md``.

These tests guard against the original failure mode: ``tool_proxy(**kwargs)``
produces a single-field ``inputSchema`` with one ``kwargs`` field, instead of
the per-field schema declared on the handler's Pydantic ``input_model``.
"""

from __future__ import annotations

import inspect

from percival_weather_mcp.server import _register_handler_with_fastmcp
from percival_weather_mcp.tools.tools_air_quality import (
    GetAirQualityDetailsToolHandler,
    GetAirQualityToolHandler,
)
from percival_weather_mcp.tools.tools_time import (
    ConvertTimeToolHandler,
    GetCurrentDateTimeToolHandler,
    GetTimeZoneInfoInput,
)
from percival_weather_mcp.tools.tools_weather import (
    GetCurrentWeatherInput,
    GetCurrentWeatherToolHandler,
    GetWeatherByDateRangeInput,
    GetWeatherDetailsInput,
)


def _register(handler):
    mcp_server = _FastMCPStub()
    _register_handler_with_fastmcp(mcp_server, handler)
    tool = mcp_server.tools[handler.name]
    return tool


class _FastMCPStub:
    """Minimal FastMCP-like target for ``_register_handler_with_fastmcp``.

    Only the bits ``_register_handler_with_fastmcp`` touches are implemented.
    The handler wrapper is just stored so the test can inspect ``tool.fn``.
    """

    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def remove_tool(self, name: str) -> None:
        self.tools.pop(name, None)

    def add_tool(self, fn, *, name, description=None):
        self.tools[name] = ToolLike(name=name, fn=fn)


class ToolLike:
    def __init__(self, name: str, fn):
        self.name = name
        self.fn = fn
        # Replicate what FastMCP exposes: a JSON schema derived from the
        # function signature via ``func_metadata``.
        self.input_schema = _signature_to_schema(fn)


def _signature_to_schema(fn) -> dict[str, object]:
    """Run FastMCP's ``func_metadata`` over ``fn`` and return its JSON schema."""
    from mcp.server.fastmcp.utilities.func_metadata import func_metadata

    metadata = func_metadata(fn)
    return metadata.arg_model.model_json_schema()


def _expected_field_names(model_cls) -> set[str]:
    return set(model_cls.model_fields.keys())


def test_proxy_for_current_weather_exposes_real_fields():
    tool = _register(GetCurrentWeatherToolHandler())
    fields = set(tool.input_schema.get("properties", {}).keys())
    assert "kwargs" not in fields, (
        "Schema regressed to the legacy kwargs-only bug"
    )
    assert fields == _expected_field_names(GetCurrentWeatherInput)


def test_proxy_for_weather_range_exposes_real_fields():
    handler_cls = (
        __import__("percival_weather_mcp.tools.tools_weather", fromlist=["X"])
        .GetWeatherByDateRangeToolHandler
    )
    tool = _register(handler_cls())
    fields = set(tool.input_schema.get("properties", {}).keys())
    assert "kwargs" not in fields
    assert fields == _expected_field_names(GetWeatherByDateRangeInput)
    required = set(tool.input_schema.get("required", []) or [])
    assert {"city", "start_date", "end_date"} <= required


def test_proxy_for_weather_details_exposes_real_fields():
    handler_cls = (
        __import__("percival_weather_mcp.tools.tools_weather", fromlist=["X"])
        .GetWeatherDetailsToolHandler
    )
    tool = _register(handler_cls())
    fields = set(tool.input_schema.get("properties", {}).keys())
    assert "kwargs" not in fields
    assert fields == _expected_field_names(GetWeatherDetailsInput)
    # ``include_forecast`` must NOT be required and must default to False.
    required = set(tool.input_schema.get("required", []) or [])
    assert "include_forecast" not in required


def test_proxy_for_air_quality_exposes_real_fields():
    tool = _register(GetAirQualityToolHandler())
    fields = set(tool.input_schema.get("properties", {}).keys())
    assert "kwargs" not in fields
    assert "city" in fields
    assert "variables" in fields


def test_proxy_for_air_quality_details_exposes_real_fields():
    tool = _register(GetAirQualityDetailsToolHandler())
    fields = set(tool.input_schema.get("properties", {}).keys())
    assert "kwargs" not in fields
    assert "city" in fields


def test_proxy_for_get_time_exposes_real_fields():
    tool = _register(GetCurrentDateTimeToolHandler())
    fields = set(tool.input_schema.get("properties", {}).keys())
    assert "kwargs" not in fields
    assert fields == _expected_field_names(GetTimeZoneInfoInput)


def test_proxy_for_convert_time_exposes_real_fields():
    tool = _register(ConvertTimeToolHandler())
    fields = set(tool.input_schema.get("properties", {}).keys())
    assert "kwargs" not in fields
    assert {"datetime_str", "from_timezone", "to_timezone"} <= fields
    required = set(tool.input_schema.get("required", []) or [])
    assert {"datetime_str", "from_timezone", "to_timezone"} <= required


def test_proxy_signature_is_rebuilt_for_fastmcp_introspection():
    """Beyond the JSON schema, FastMCP also uses ``__signature__`` to drive
    ``func_metadata``; confirm we set it too so the schema is consistent."""
    handler = GetCurrentWeatherToolHandler()
    tool = _register(handler)
    sig = inspect.signature(tool.fn)
    assert "kwargs" not in sig.parameters
    assert "city" in sig.parameters
    # The Parameter kind we set is KEYWORD_ONLY — FastMCP requires the args to
    # be passed as keyword arguments.
    assert sig.parameters["city"].kind == inspect.Parameter.KEYWORD_ONLY
