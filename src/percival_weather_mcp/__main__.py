"""Module entry point for ``python -m percival_weather_mcp``.

The CLI turns an invalid environment into a controlled operator message and a
non-zero exit code, instead of letting a raw traceback reach the container
logs.
"""

from __future__ import annotations

import asyncio
import sys


def run_cli() -> int:
    """Run the server CLI and return the process exit code."""
    from .config import ConfigurationError
    from .server import main

    try:
        asyncio.run(main())
    except ConfigurationError as exc:
        print(f"percival-weather-mcp: configuration error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli())
