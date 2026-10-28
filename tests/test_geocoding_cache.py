"""Tests for the process-wide geocoding cache (F-009).

Every tool handler used to own its own cache, so the number of geocoding
calls grew with the number of tools involved in a conversation — against a
public, rate-limited API. The cache is now shared by the whole process.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Iterator

import pytest
import respx

from percival_weather_mcp import config
from percival_weather_mcp.http_client import get_geocoding_cache, reset_shared_state

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

FORECAST_BODY = {
    "hourly": {
        "time": ["2026-01-01T00:00", "2026-01-01T01:00"],
        "temperature_2m": [21.0, 22.0],
        "weather_code": [2, 3],
    }
}


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    reset_shared_state()
    monkeypatch.setattr(
        config,
        "_runtime_settings",
        config.Settings.from_env(http_max_retries=0),
        raising=False,
    )
    yield
    reset_shared_state()


@contextlib.contextmanager
def _mock_upstream() -> Iterator[object]:
    """Mock both upstream endpoints and yield the two route objects."""
    with respx.mock(assert_all_called=False) as mock:
        geo = mock.get(GEO_URL).respond(
            200, json={"results": [{"latitude": -23.55, "longitude": -46.63}]}
        )
        forecast = mock.get(FORECAST_URL).respond(200, json=FORECAST_BODY)
        yield geo, forecast


@pytest.mark.asyncio
async def test_two_tools_share_one_geocoding_call():
    """Four logical queries for one city across two tools cost one geocoding call."""
    from percival_weather_mcp.tools.tools_weather import (
        GetCurrentWeatherToolHandler,
        GetWeatherDetailsToolHandler,
    )

    with _mock_upstream() as (geo, _forecast):
        current = GetCurrentWeatherToolHandler()
        details = GetWeatherDetailsToolHandler()
        for _ in range(2):
            await current.run_tool({"city": "Cidade Teste"})
            await details.run_tool({"city": "Cidade Teste"})

    assert geo.call_count == 1, "the geocoding cache must be shared between handlers"


@pytest.mark.asyncio
async def test_different_cities_are_cached_separately():
    from percival_weather_mcp.tools.tools_weather import GetCurrentWeatherToolHandler

    with _mock_upstream() as (geo, _forecast):
        handler = GetCurrentWeatherToolHandler()
        await handler.run_tool({"city": "Cidade Alfa"})
        await handler.run_tool({"city": "Cidade Beta"})
        await handler.run_tool({"city": "Cidade Alfa"})

    assert geo.call_count == 2


@pytest.mark.asyncio
async def test_expired_entry_is_geocoded_again(monkeypatch):
    """The TTL keeps working after the cache became process-wide."""
    from percival_weather_mcp.tools.tools_weather import GetCurrentWeatherToolHandler

    monkeypatch.setattr(
        config,
        "_runtime_settings",
        config.Settings.from_env(http_max_retries=0, geo_cache_ttl_seconds=0.05),
        raising=False,
    )
    reset_shared_state()

    with _mock_upstream() as (geo, _forecast):
        handler = GetCurrentWeatherToolHandler()
        await handler.run_tool({"city": "Cidade Teste"})
        await handler.run_tool({"city": "Cidade Teste"})
        assert geo.call_count == 1
        await asyncio.sleep(0.08)
        await handler.run_tool({"city": "Cidade Teste"})

    assert geo.call_count == 2, "an expired entry must not be served"


@pytest.mark.asyncio
async def test_concurrent_lookups_do_not_contaminate_the_cache():
    """Concurrent callers must all observe the same coordinates."""
    from percival_weather_mcp.tools.tools_weather import GetCurrentWeatherToolHandler

    with _mock_upstream():
        handlers = [GetCurrentWeatherToolHandler() for _ in range(6)]
        results = await asyncio.gather(
            *(handler.run_tool({"city": "Cidade Teste"}) for handler in handlers)
        )

    cache = get_geocoding_cache()
    assert len(cache) == 1
    assert cache.get("Cidade Teste") == (-23.55, -46.63)
    for result in results:
        assert result


@pytest.mark.asyncio
async def test_cache_is_bounded_by_the_configured_max_size(monkeypatch):
    """The size bound survives the move to a shared cache."""
    from percival_weather_mcp.tools.tools_weather import GetCurrentWeatherToolHandler

    monkeypatch.setattr(
        config,
        "_runtime_settings",
        config.Settings.from_env(http_max_retries=0, geo_cache_max_size=2),
        raising=False,
    )
    reset_shared_state()

    with _mock_upstream():
        handler = GetCurrentWeatherToolHandler()
        for city in ("Cidade A", "Cidade B", "Cidade C"):
            await handler.run_tool({"city": city})

    assert len(get_geocoding_cache()) <= 2
