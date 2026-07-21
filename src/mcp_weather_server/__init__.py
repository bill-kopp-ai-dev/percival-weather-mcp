"""Compatibility package for legacy imports of ``mcp_weather_server``.

The implementation lives in :mod:`percival_weather_mcp`; this module exists
solely to preserve the public ``mcp_weather_server`` import path for existing
integrators and will be removed in a future major release.
"""

from percival_weather_mcp import async_main, main

__all__ = ["async_main", "main"]
