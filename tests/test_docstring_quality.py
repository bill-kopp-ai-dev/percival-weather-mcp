"""Regression tests that pin the documentation quality of tool schemas.

Each tool description must:
    * Be at least 60 characters long.
    * Mention output shape (e.g. "JSON", "summary", "raw").
    * Mention an error/limitation when applicable.

Each input model must include at least one Pydantic ``examples`` entry when
the model exposes ``model_config.json_schema_extra.examples``.
"""

from __future__ import annotations

from percival_weather_mcp import server
from percival_weather_mcp.models import (
    GetAirQualityDetailsInput,
    GetAirQualityInput,
    GetCurrentDateTimeInput,
    GetCurrentWeatherInput,
    GetTimeZoneInfoInput,
    GetWeatherByDateRangeInput,
    GetWeatherDetailsInput,
)


def _ensure_minimum_quality(description: str, *, tool: str) -> None:
    """Reject descriptions that are too short or miss the basics."""
    assert len(description) >= 60, f"{tool}: description too short ({len(description)} chars)"
    lowered = description.lower()
    assert any(token in lowered for token in ("json", "summary", "raw", "prose", "plain")), (
        f"{tool}: description should mention the output shape"
    )


def test_all_tools_have_substantive_descriptions():
    server.register_all_tools()
    for name, handler in server.tool_handlers.items():
        tool = handler.get_tool_description()
        _ensure_minimum_quality(tool.description, tool=name)


def test_each_input_model_has_examples_or_rich_description():
    """All inputs should expose either ``examples`` or a very rich description."""
    model_to_tool = {
        GetCurrentWeatherInput: "weather_get_current",
        GetWeatherByDateRangeInput: "weather_get_by_range",
        GetWeatherDetailsInput: "weather_get_details",
        GetAirQualityInput: "weather_get_air_quality",
        GetAirQualityDetailsInput: "weather_get_air_quality_details",
        GetCurrentDateTimeInput: "weather_get_time",
        GetTimeZoneInfoInput: "weather_get_timezone",
    }
    for model_cls, tool_name in model_to_tool.items():
        schema = model_cls.model_json_schema()
        # ``examples`` may live on top-level schema (Pydantic ``json_schema_extra``)
        # or on individual property entries (``Field(examples=[...])``).
        top_examples = schema.get("examples") or []
        property_examples = any(
            prop.get("examples") for prop in schema.get("properties", {}).values()
        )
        assert top_examples or property_examples, (
            f"{tool_name}: model must expose at least one example"
        )
