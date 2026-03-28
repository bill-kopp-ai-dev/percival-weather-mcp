"""Compatibility package for legacy imports of ``mcp_weather_server``."""

from percival_weather_mcp import async_main, main

__all__ = ["main", "async_main"]
