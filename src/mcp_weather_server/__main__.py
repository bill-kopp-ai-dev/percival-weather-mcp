"""Compatibility entrypoint for ``python -m mcp_weather_server``."""

import asyncio

from percival_weather_mcp.server import main

if __name__ == "__main__":
    asyncio.run(main())
