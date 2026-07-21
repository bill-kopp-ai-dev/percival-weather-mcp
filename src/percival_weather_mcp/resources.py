"""MCP resources exposed by the server.

Resources are read-only data the agent can consult on demand. They help the
agent interpret raw API payloads without having to memorise reference tables.

Each resource is registered via :meth:`WeatherFastMCP.add_resource` in
:mod:`percival_weather_mcp.server` and exposed under the ``weather://`` URI
scheme so it is easy to identify them in the agent's logs.

Available resources:

* ``weather://codes`` — WMO weather code reference table.
* ``weather://aqi`` — Air-quality risk bands per pollutant.
* ``weather://timezones`` — Curated list of common IANA timezones.
* ``weather://schema/{tool_name}`` — Top-level keys for the detailed tools.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from .knowledge_base import (
    aqi_table,
    timezone_table,
    tool_response_schemas,
    weather_code_table,
)

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


RESOURCE_PREFIX = "weather://"


def _serialise(payload: object) -> str:
    """Render an arbitrary Python object as a JSON string suitable for resources."""
    return json.dumps(payload, indent=2, ensure_ascii=False)


def register_resources(mcp_server: FastMCP) -> None:
    """Attach every static resource to the given FastMCP server."""

    @mcp_server.resource(
        f"{RESOURCE_PREFIX}codes",
        name="weather_codes",
        description=(
            "WMO weather code reference table used by the Open-Meteo API. "
            "Each entry has a numeric ``code`` and a human-readable ``description``. "
            "Consult this resource whenever the agent needs to translate a numeric "
            "code returned by ``weather_get_details`` or ``weather_get_by_range`` "
            "into plain text (e.g. code 95 → 'Thunderstorm: slight or moderate')."
        ),
    )
    def weather_codes() -> str:
        return _serialise({"codes": weather_code_table()})

    @mcp_server.resource(
        f"{RESOURCE_PREFIX}aqi",
        name="weather_aqi",
        description=(
            "Air-quality risk bands per pollutant (PM2.5, PM10, ozone, NO2, SO2, CO) "
            "following WHO 2021 / EPA breakpoints. Each band has ``min``, ``max``, "
            "``label`` and an optional ``advice`` recommendation. Use this resource "
            "when the user asks whether the air is safe for outdoor activity."
        ),
    )
    def weather_aqi() -> str:
        return _serialise({"bands": aqi_table()})

    @mcp_server.resource(
        f"{RESOURCE_PREFIX}timezones",
        name="weather_timezones",
        description=(
            "Curated list of commonly-used IANA timezone names with display label "
            "and typical UTC offset (DST-aware ranges shown as ``+HH:MM/+HH:MM``). "
            "Use this resource whenever the agent must choose an IANA name for "
            "``weather_convert_time`` or ``weather_get_time``."
        ),
    )
    def weather_timezones() -> str:
        return _serialise({"timezones": timezone_table()})

    @mcp_server.resource(
        f"{RESOURCE_PREFIX}schema/{{tool_name}}",
        name="weather_tool_schema",
        description=(
            "Top-level keys returned by the detailed weather/air-quality tools. "
            "Pass ``tool_name`` as one of: ``weather_get_details``, "
            "``weather_get_by_range``, ``weather_get_air_quality_details``. "
            "Consult this resource before calling those tools so the agent can "
            "plan which fields to extract."
        ),
    )
    def weather_tool_schema(tool_name: str) -> str:
        schemas = tool_response_schemas()
        if tool_name not in schemas:
            return _serialise(
                {
                    "error": f"unknown tool '{tool_name}'",
                    "available": list(schemas.keys()),
                }
            )
        return _serialise({"tool": tool_name, **schemas[tool_name]})
