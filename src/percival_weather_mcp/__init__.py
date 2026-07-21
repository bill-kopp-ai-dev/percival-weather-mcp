"""Percival Weather MCP server package."""

from __future__ import annotations

import asyncio

from .__version__ import __version__
from .server import app
from .server import main as async_main


def main() -> None:
    """Synchronous entry point used by ``[project.scripts]``."""
    asyncio.run(async_main())


__all__ = ["__version__", "app", "async_main", "main"]
