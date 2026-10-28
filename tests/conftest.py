"""Shared pytest fixtures."""

from __future__ import annotations

import os

import pytest

# Ensure tests never reach out to the real Open-Meteo endpoints unless
# explicitly opted in via ``PERCIVAL_WEATHER_RUN_NETWORK_TESTS=1``.
os.environ.setdefault("MCP_WEATHER_ENABLE_METRICS", "false")
os.environ.setdefault("MCP_WEATHER_RATE_LIMIT_PER_MINUTE", "10000")


@pytest.fixture(autouse=True)
def _reset_shared_state():
    """Drop the process-wide singletons between tests.

    The geocoding cache is shared by the whole server (F-009), so a test that
    geocoded a city would otherwise leak that entry into the next one.
    """
    from percival_weather_mcp.http_client import reset_shared_state

    reset_shared_state()
    yield
    reset_shared_state()
