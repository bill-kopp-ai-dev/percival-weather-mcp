"""Tests for the resilient HTTP client (retries, breaker, semaphore)."""

from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from percival_weather_mcp import config
from percival_weather_mcp.http_client import (
    CircuitBreaker,
    CircuitOpenError,
    ResilientHttpClient,
    get_geo_breaker,
    reset_shared_state,
)


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    """Force a clean settings + breaker instance per test."""
    reset_shared_state()
    monkeypatch.setattr(
        config,
        "_runtime_settings",
        config.Settings.from_env(
            http_max_retries=1,
            http_backoff_base=0.001,
            http_backoff_cap=0.002,
            http_max_concurrency=2,
        ),
        raising=False,
    )
    yield
    reset_shared_state()


@pytest.mark.asyncio
async def test_get_json_returns_payload():
    with respx.mock(base_url="https://example.test") as mock:
        route = mock.get("/ping").respond(200, json={"ok": True})
        async with ResilientHttpClient(name="test") as client:
            data = await client.get_json("https://example.test/ping")
        assert data == {"ok": True}
        assert route.call_count == 1


@pytest.mark.asyncio
async def test_retries_then_succeeds():
    with respx.mock(base_url="https://example.test") as mock:
        route = mock.get("/flaky").mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(200, json={"ok": True}),
            ]
        )
        async with ResilientHttpClient(name="test") as client:
            data = await client.get_json("https://example.test/flaky")
        assert data == {"ok": True}
        assert route.call_count == 2


@pytest.mark.asyncio
async def test_raises_after_exhausting_retries():
    with respx.mock(base_url="https://example.test") as mock:
        route = mock.get("/boom").mock(return_value=httpx.Response(500))
        async with ResilientHttpClient(name="test") as client:
            with pytest.raises(ValueError):
                await client.get_json("https://example.test/boom")
        # attempts = 1 + max_retries
        assert route.call_count == 2


@pytest.mark.asyncio
async def test_circuit_breaker_opens_and_short_circuits():
    breaker = CircuitBreaker(fail_threshold=2, reset_seconds=10)
    with respx.mock(base_url="https://example.test") as mock:
        mock.get("/geo").mock(return_value=httpx.Response(500))
        async with ResilientHttpClient(name="geo") as client:
            for _ in range(2):
                with pytest.raises(ValueError):
                    await client.get_json(
                        "https://example.test/geo", breaker=breaker
                    )
            with pytest.raises(CircuitOpenError):
                await client.get_json(
                    "https://example.test/geo", breaker=breaker
                )


@pytest.mark.asyncio
async def test_breaker_resets_after_window():
    breaker = CircuitBreaker(fail_threshold=1, reset_seconds=0.2)
    with respx.mock(base_url="https://example.test") as mock:
        route = mock.get("/geo").mock(
            side_effect=[
                httpx.Response(500),
                httpx.Response(500),
                httpx.Response(200, json={"ok": True}),
            ]
        )
        async with ResilientHttpClient(name="geo") as client:
            with pytest.raises(ValueError):
                await client.get_json(
                    "https://example.test/geo", breaker=breaker
                )
            await asyncio.sleep(0.25)
            data = await client.get_json(
                "https://example.test/geo", breaker=breaker
            )
        assert data == {"ok": True}
        assert route.call_count == 3


def test_get_geo_breaker_is_singleton():
    breaker = get_geo_breaker()
    assert get_geo_breaker() is breaker
