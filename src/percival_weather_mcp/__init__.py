"""Percival Weather MCP server package."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from .__version__ import __version__
from .server import main as async_main

if TYPE_CHECKING:
    # ``app`` is populated by :func:`server.main` at runtime; importing it
    # eagerly would freeze the reference to the initial ``None`` placeholder
    # (see https://docs.python.org/3/reference/import.html for the underlying
    # import-binding semantics). Re-export it lazily via :func:`__getattr__`
    # so callers always see the live module-level instance.
    from .server import app as app


def __getattr__(name: str) -> Any:
    """Resolve ``percival_weather_mcp.app`` against the live ``server.app``.

    A flat ``from .server import app`` would copy the reference at import
    time, which is ``None`` until :func:`server.main` runs. PEP 562 lets us
    defer the lookup so consumers always see the current value.
    """
    if name == "app":
        from .server import app as _app

        return _app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def main() -> None:
    """Synchronous entry point used by ``[project.scripts]``."""
    asyncio.run(async_main())


__all__ = ["__version__", "app", "async_main", "main"]
