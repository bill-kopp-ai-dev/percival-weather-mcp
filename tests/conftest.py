"""Shared pytest fixtures."""

from __future__ import annotations

import os

# Ensure tests never reach out to the real Open-Meteo endpoints unless
# explicitly opted in via ``PERCIVAL_WEATHER_RUN_NETWORK_TESTS=1``.
os.environ.setdefault("MCP_WEATHER_ENABLE_METRICS", "false")
os.environ.setdefault("MCP_WEATHER_RATE_LIMIT_PER_MINUTE", "10000")
