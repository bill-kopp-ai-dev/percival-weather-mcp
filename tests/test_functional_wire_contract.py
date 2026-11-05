"""Functional regression through actual MCP session serialization and discovery."""

import json
from datetime import datetime, timezone

import jsonschema
import pytest
import respx
from mcp.shared.memory import create_connected_server_and_client_session

from percival_weather_mcp import config, series
from percival_weather_mcp.models import GetAirQualityInput, GetWeatherByDateRangeInput
from percival_weather_mcp.server import create_fastmcp_server, register_all_tools


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    monkeypatch.setattr(
        series, "utc_now", lambda: datetime(2026, 11, 5, 21, 20, tzinfo=timezone.utc)
    )


async def test_schema_discovery_preserves_constraints_and_optional_defaults():
    register_all_tools()
    app = create_fastmcp_server()
    tools = {t.name: t for t in await app.list_tools()}
    assert len(tools) == 9
    assert len(await app.list_prompts()) == 3 and len(await app.list_resources()) == 3
    assert len(await app.list_resource_templates()) == 1
    for name, model in [
        ("weather_get_air_quality", GetAirQualityInput),
        ("weather_get_by_range", GetWeatherByDateRangeInput),
    ]:
        actual = tools[name].inputSchema
        expected = model.model_json_schema()
        assert set(actual["properties"]) == set(expected["properties"])
        for field in expected["properties"]:
            assert actual["properties"][field] == expected["properties"][field]
        assert actual["required"] == expected["required"]
    aq_schema = tools["weather_get_air_quality"].inputSchema["properties"]["variables"]
    assert aq_schema["anyOf"][0]["minItems"] == 1
    assert aq_schema["anyOf"][0]["maxItems"] == 9
    assert (
        tools["weather_get_by_range"].inputSchema["properties"]["sample_mode"]["default"] == "first"
    )


@pytest.mark.parametrize(
    "name,args,rule",
    [
        ("weather_get_current", {"city": "private<city>"}, "unsupported"),
        ("weather_get_current", {"city": "x" * 201}, "200"),
        ("weather_get_air_quality", {"city": "Test", "variables": []}, "at least 1"),
        ("weather_get_air_quality_details", {"city": "Test", "variables": []}, "at least 1"),
        (
            "weather_get_air_quality",
            {"city": "Test", "variables": ["secret-invalid-pollutant"]},
            "Input should be",
        ),
        (
            "weather_get_by_range",
            {"city": "Test", "start_date": "2026-11-06", "end_date": "2026-11-05"},
            "on or after",
        ),
        (
            "weather_get_by_range",
            {"city": "Test", "start_date": "2020-01-01", "end_date": "2020-01-01"},
            "window",
        ),
    ],
)
async def test_wire_validation_is_actionable_without_input_dump(name, args, rule):
    register_all_tools()
    app = create_fastmcp_server()
    with respx.mock(assert_all_called=False) as mock:
        async with create_connected_server_and_client_session(app._mcp_server) as client:
            await client.initialize()
            result = await client.call_tool(name, args)
        assert not mock.calls
    assert result.isError
    text = result.content[0].text
    assert rule in text
    assert (
        "input_value" not in text
        and "private<city>" not in text
        and "secret-invalid-pollutant" not in text
    )


async def test_mcp_outputs_validate_against_their_resource_schemas(monkeypatch):
    register_all_tools()
    app = create_fastmcp_server()
    with respx.mock as mock:
        mock.get("https://geocoding-api.open-meteo.com/v1/search").respond(
            200,
            json={
                "results": [
                    {"name": "Paris", "country_code": "FR", "latitude": 1.0, "longitude": 2.0}
                ]
            },
        )
        mock.get("https://api.open-meteo.com/v1/forecast").respond(
            200,
            json={
                "hourly": {
                    "time": ["2026-11-05T21:00", "2026-11-05T22:00"],
                    "weather_code": [0, 0],
                    "temperature_2m": [0, 1],
                }
            },
        )
        raw_aq = {
            "unknown_provider_key": {"kept": True},
            "hourly": {
                "time": ["2026-11-05T21:00", "2026-11-05T22:00"],
                "pm10": [0, None],
                "us_aqi_pm10": [42, None],
            },
        }
        mock.get("https://air-quality-api.open-meteo.com/v1/air-quality").respond(200, json=raw_aq)
        async with create_connected_server_and_client_session(app._mcp_server) as client:
            await client.initialize()
            for name, args in [
                ("weather_get_details", {"city": "Paris", "include_forecast": True}),
                (
                    "weather_get_by_range",
                    {
                        "city": "Paris",
                        "start_date": "2026-11-05",
                        "end_date": "2026-11-05",
                        "sample_mode": "spread",
                    },
                ),
                ("weather_get_air_quality_details", {"city": "Paris", "variables": ["pm10"]}),
            ]:
                result = await client.call_tool(name, args)
                assert not result.isError
                payload = json.loads(result.content[0].text)
                resource = await client.read_resource(f"weather://schema/{name}")
                schema = json.loads(resource.contents[0].text)
                jsonschema.Draft202012Validator(schema["json_schema"]).validate(payload)
                assert set(payload) <= set(schema["top_level_keys"])
                assert payload["source"]["data_kind"] == "model"
                if "full_data" in payload:
                    assert payload["full_data"] == raw_aq
            compact = await client.call_tool("weather_get_current", {"city": "Paris"})
            assert "Clear sky" in compact.content[0].text and "UTC" in compact.content[0].text

    # Runtime-configured duration must also reach prompt/resource metadata.
    monkeypatch.setattr(config, "_runtime_settings", config.Settings(max_date_range_days=2))
    configured = create_fastmcp_server()
    prompt = await configured.get_prompt(
        "weather_analysis", {"city": "Paris", "start_date": "2026-11-05", "end_date": "2026-11-05"}
    )
    assert "≤ 2 days" in prompt.messages[0].content.text
    schema = await configured.read_resource("weather://schema/weather_get_by_range")
    assert "at most 2 days" in json.loads(schema[0].content)["notes"]


async def test_status_is_liveness_even_when_upstream_is_down(monkeypatch):
    monkeypatch.setattr(config, "_runtime_settings", config.Settings(http_max_retries=0))
    register_all_tools()
    app = create_fastmcp_server()
    with respx.mock as mock:
        mock.get("https://geocoding-api.open-meteo.com/v1/search").respond(503)
        async with create_connected_server_and_client_session(app._mcp_server) as client:
            await client.initialize()
            data = await client.call_tool("weather_get_current", {"city": "Test"})
            status = await client.call_tool("weather_get_status", {})
    assert data.isError and "503" in data.content[0].text
    assert not status.isError
    assert (
        "liveness" in status.content[0].text
        and "Upstream readiness not checked" in status.content[0].text
    )
