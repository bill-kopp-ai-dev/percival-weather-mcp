"""Regression tests for round-3 bug fixes."""

from __future__ import annotations

import asyncio

import pytest
import respx

from percival_weather_mcp import server
from percival_weather_mcp.http_client import ResilientHttpClient


def test_create_fastmcp_server_returns_independent_instances():
    """Regression: ``create_fastmcp_server`` must NOT return the same object
    across calls (issue #1 — singleton state pollution).
    """
    first = server.create_fastmcp_server()
    second = server.create_fastmcp_server()
    assert first is not second
    # Each instance has its own prompt manager.
    assert first._prompt_manager is not second._prompt_manager
    assert first._resource_manager is not second._resource_manager


def test_register_all_tools_does_not_mutate_module_app_when_none():
    """Regression: registering tools when ``app is None`` must not crash."""
    original_app = server.app
    server.app = None
    try:
        server.tool_handlers.clear()
        server.register_all_tools()
        # App should still be None — registering tools does not create it.
        assert server.app is None
        # But the handlers were added to the in-memory registry.
        assert "weather_get_current" in server.tool_handlers
    finally:
        server.tool_handlers.clear()
        server.app = original_app


@pytest.mark.asyncio
async def test_record_http_request_counts_all_status_codes(monkeypatch):
    """Regression: ``record_http_request`` must be called for every status code
    (issue #3), not only 200.
    """
    from percival_weather_mcp import observability
    from percival_weather_mcp.config import Settings

    # Force metrics enabled by patching observability.get_settings.
    monkeypatch.setattr(
        observability,
        "get_settings",
        lambda: Settings.from_env(enable_metrics=True),
    )
    observability.reset_metrics()
    metrics = observability.get_metrics()
    assert metrics.enabled, "metrics must be enabled for this regression test"

    fast_settings = Settings.from_env(http_max_retries=0)
    with respx.mock(base_url="https://example.test") as mock:
        mock.get("/boom").respond(500)
        async with ResilientHttpClient(settings=fast_settings, name="recording-test") as client:
            with pytest.raises(ValueError):
                await client.get_json("https://example.test/boom")

    value = metrics.http_requests.labels(upstream="recording-test", status="500")._value.get()
    assert value >= 1, "5xx requests must be counted in the HTTP metrics"
    observability.reset_metrics()


def test_convert_time_now_with_whitespace():
    """Regression: ``\" now \"`` must be treated as ``now`` (issue #4)."""
    from percival_weather_mcp.tools.tools_time import ConvertTimeToolHandler

    handler = ConvertTimeToolHandler()
    # Should not raise — must accept the leading/trailing whitespace.
    result = asyncio.run(
        handler.run_tool(
            {
                "datetime_str": "  now  ",
                "from_timezone": "UTC",
                "to_timezone": "America/Sao_Paulo",
            }
        )
    )
    assert result
    # Find a text content with the conversion payload.
    import json

    payload = json.loads(result[0].text)
    assert "converted_datetime" in payload


def test_normalize_aq_variables_accepts_tuple():
    """Regression: ``_normalize_aq_variables`` must accept any Sequence[str]."""
    from percival_weather_mcp.tools.tools_air_quality import _normalize_aq_variables

    result = _normalize_aq_variables(("pm2_5", "ozone"), ["pm2_5", "pm10"])
    assert result == ["pm2_5", "ozone"]
