"""Regression tests for ``tool_export.build_primitives_document``.

These tests guard against two related bugs:

1. ``build_primitives_document`` previously iterated only over the
   ``tool_handlers`` registry, which does not include the synthetic
   ``weather_get_status`` tool that ``_register_status_tool`` attaches
   directly to the FastMCP instance. The resulting ``docs/tools.json``
   dropped the status tool, which made ``test_mcp_yaml.py::test_manifest
   _tools_match_server_source_of_truth`` fail (manifest advertised
   ``weather_get_status`` but the server dump did not).

2. The primitives dump must remain a JSON-serialisable document so the
   ``tool_export`` CLI helper continues to work.
"""

from __future__ import annotations

import json
import subprocess
import sys

from percival_weather_mcp import tool_export


def test_primitives_document_is_json_serialisable():
    document = tool_export.build_primitives_document()
    # Must be JSON-encodable without a custom encoder.
    payload = json.dumps(document)
    assert payload


def test_primitives_document_includes_status_tool():
    document = tool_export.build_primitives_document()
    names = {tool["name"] for tool in document["tools"]}
    assert "weather_get_status" in names, (
        "the synthetic status tool is registered directly on the FastMCP "
        "instance and must show up in the primitives dump"
    )


def test_primitives_document_lists_every_data_tool():
    document = tool_export.build_primitives_document()
    names = {tool["name"] for tool in document["tools"]}
    expected = {
        "weather_get_current",
        "weather_get_by_range",
        "weather_get_details",
        "weather_get_time",
        "weather_get_timezone",
        "weather_convert_time",
        "weather_get_air_quality",
        "weather_get_air_quality_details",
        "weather_get_status",
    }
    missing = expected - names
    assert not missing, f"primitives dump is missing tools: {sorted(missing)}"


def test_tool_export_cli_writes_valid_json(capsys):
    """The ``python -m percival_weather_mcp.tool_export`` CLI must emit JSON."""
    result = subprocess.run(
        [sys.executable, "-m", "percival_weather_mcp.tool_export"],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert "tools" in payload
    names = {tool["name"] for tool in payload["tools"]}
    assert "weather_get_status" in names
