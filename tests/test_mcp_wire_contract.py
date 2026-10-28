"""Protocol-level tests for the MCP contract of the server.

These run a real MCP session over the SDK's in-memory transport, so the
exchanges go through the same session/serialisation layer as the wire. The
byte-level proof against the built image lives in
``scripts/verification/wx_resources_probe.py``.

They pin three behaviours:

* ``serverInfo`` advertises the **product** version, not the MCP SDK one;
* ``prompts/get`` without a required argument is an *invalid params* error;
* ``resources/read`` of a template target that does not exist is a *resource
  not found* error — never a successful read carrying an error payload.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from mcp import McpError
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import INVALID_PARAMS

from percival_weather_mcp import server as weather_server
from percival_weather_mcp.__version__ import __version__


@asynccontextmanager
async def mcp_session() -> AsyncIterator[tuple[object, object]]:
    """Yield a connected MCP client session bound to a fresh server."""
    weather_server.register_all_tools()
    app = weather_server.create_fastmcp_server()
    async with create_connected_server_and_client_session(app._mcp_server) as client:
        init = await client.initialize()
        yield client, init


@pytest.mark.asyncio
async def test_server_info_reports_the_product_version():
    """F-008 regression: the handshake must not report the SDK version."""
    async with mcp_session() as (_client, init):
        assert init.serverInfo.name == "percival-weather-mcp"
        assert init.serverInfo.version == __version__
        assert init.serverInfo.version != "1.30.0"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "missing"),
    [
        ("weather_quick_answer", "city"),
        ("weather_analysis", "city"),
    ],
)
async def test_prompt_without_required_argument_is_an_invalid_params_error(
    name: str, missing: str
) -> None:
    """A missing prompt argument must be an error, not an empty answer."""
    async with mcp_session() as (client, _init):
        with pytest.raises(McpError) as excinfo:
            await client.get_prompt(name, {})
    assert excinfo.value.error.code == INVALID_PARAMS
    assert missing in excinfo.value.error.message


@pytest.mark.asyncio
async def test_prompt_with_all_arguments_still_renders() -> None:
    async with mcp_session() as (client, _init):
        result = await client.get_prompt("weather_quick_answer", {"city": "Cidade Teste"})
    assert len(result.messages) == 2
    assert "Cidade Teste" in result.messages[1].content.text


@pytest.mark.asyncio
async def test_prompt_without_arguments_still_renders() -> None:
    """``weather_unit_conversion`` has no required argument: it must work."""
    async with mcp_session() as (client, _init):
        result = await client.get_prompt("weather_unit_conversion", {})
    assert len(result.messages) == 2


@pytest.mark.asyncio
async def test_unknown_prompt_is_an_invalid_params_error() -> None:
    async with mcp_session() as (client, _init):
        with pytest.raises(McpError) as excinfo:
            await client.get_prompt("weather_does_not_exist", {})
    assert excinfo.value.error.code == INVALID_PARAMS


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "uri",
    [
        "weather://schema/weather_get_current",
        "weather://schema/inexistente",
    ],
)
async def test_unknown_resource_template_target_is_a_resource_not_found_error(uri: str) -> None:
    """F-013 regression: an unknown target must not be a successful read."""
    async with mcp_session() as (client, _init):
        with pytest.raises(McpError) as excinfo:
            await client.read_resource(uri)
    assert excinfo.value.error.code == -32002
    assert "unknown tool" in excinfo.value.error.message


@pytest.mark.asyncio
async def test_unknown_resource_uri_is_a_resource_not_found_error() -> None:
    async with mcp_session() as (client, _init):
        with pytest.raises(McpError) as excinfo:
            await client.read_resource("weather://nao-existe")
    assert excinfo.value.error.code == -32002


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("uri", "minimum_length"),
    [
        ("weather://codes", 1000),
        ("weather://aqi", 1000),
        ("weather://timezones", 1000),
        ("weather://schema/weather_get_details", 100),
        ("weather://schema/weather_get_by_range", 100),
        ("weather://schema/weather_get_air_quality_details", 100),
    ],
)
async def test_known_resources_are_still_readable(uri: str, minimum_length: int) -> None:
    """The valid cases must keep working after the error-contract change."""
    async with mcp_session() as (client, _init):
        result = await client.read_resource(uri)
    text = result.contents[0].text
    assert len(text) >= minimum_length
    assert not result.contents[0].text.lstrip().startswith('{"error"')
