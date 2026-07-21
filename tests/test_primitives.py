"""Tests for MCP primitives (prompts and resources)."""

from __future__ import annotations

import json

import pytest

from percival_weather_mcp.prompts import register_prompts
from percival_weather_mcp.resources import register_resources
from percival_weather_mcp.server import create_fastmcp_server


@pytest.fixture
def mcp_server():
    server = create_fastmcp_server()
    register_prompts(server)
    register_resources(server)
    return server


@pytest.mark.asyncio
async def test_all_prompts_registered(mcp_server):
    names = {p.name for p in await mcp_server.list_prompts()}
    assert "weather_quick_answer" in names
    assert "weather_analysis" in names
    assert "weather_unit_conversion" in names


@pytest.mark.asyncio
async def test_all_static_resources_registered(mcp_server):
    uris = {str(r.uri) for r in await mcp_server.list_resources()}
    assert "weather://codes" in uris
    assert "weather://aqi" in uris
    assert "weather://timezones" in uris


@pytest.mark.asyncio
async def test_resource_template_registered(mcp_server):
    templates_uris = {str(t.uriTemplate) for t in await mcp_server.list_resource_templates()}
    assert "weather://schema/{tool_name}" in templates_uris


@pytest.mark.asyncio
async def test_weather_codes_resource_returns_valid_json(mcp_server):
    result = await mcp_server.read_resource("weather://codes")
    payload = json.loads(result[0].content)
    assert "codes" in payload
    assert any(entry["code"] == 0 for entry in payload["codes"])
    assert any(entry["code"] == 95 for entry in payload["codes"])


@pytest.mark.asyncio
async def test_aqi_resource_contains_main_pollutants(mcp_server):
    result = await mcp_server.read_resource("weather://aqi")
    payload = json.loads(result[0].content)
    bands = payload["bands"]
    assert "pm2_5" in bands
    assert "pm10" in bands
    assert "ozone" in bands
    for pollutant, entries in bands.items():
        assert entries, f"{pollutant} has no bands"


@pytest.mark.asyncio
async def test_timezones_resource_includes_common_zones(mcp_server):
    result = await mcp_server.read_resource("weather://timezones")
    payload = json.loads(result[0].content)
    iana_names = {entry["iana"] for entry in payload["timezones"]}
    assert "UTC" in iana_names
    assert "America/Sao_Paulo" in iana_names
    assert "Europe/London" in iana_names
    assert "Asia/Tokyo" in iana_names


@pytest.mark.asyncio
async def test_schema_template_returns_keys_for_known_tool(mcp_server):
    result = await mcp_server.read_resource("weather://schema/weather_get_details")
    payload = json.loads(result[0].content)
    assert payload["tool"] == "weather_get_details"
    assert "top_level_keys" in payload
    assert "temperature_c" in payload["top_level_keys"]


@pytest.mark.asyncio
async def test_schema_template_returns_error_for_unknown_tool(mcp_server):
    result = await mcp_server.read_resource("weather://schema/weather_does_not_exist")
    payload = json.loads(result[0].content)
    assert "error" in payload
    assert "weather_get_details" in payload["available"]


@pytest.mark.asyncio
async def test_weather_quick_answer_prompt(mcp_server):
    result = await mcp_server.get_prompt("weather_quick_answer", {"city": "London"})
    assert result.messages
    user = next(m for m in result.messages if m.role == "user")
    assert "London" in user.content.text


@pytest.mark.asyncio
async def test_weather_analysis_prompt(mcp_server):
    result = await mcp_server.get_prompt(
        "weather_analysis",
        {"city": "Lisbon", "start_date": "2026-01-01", "end_date": "2026-01-07"},
    )
    assert result.messages
    assistant = next(m for m in result.messages if m.role == "assistant")
    assert "weather_get_by_range" in assistant.content.text


@pytest.mark.asyncio
async def test_weather_unit_conversion_prompt_defaults(mcp_server):
    result = await mcp_server.get_prompt("weather_unit_conversion", {})
    assert result.messages
    user = next(m for m in result.messages if m.role == "user")
    assert "now" in user.content.text
    assert "UTC" in user.content.text
