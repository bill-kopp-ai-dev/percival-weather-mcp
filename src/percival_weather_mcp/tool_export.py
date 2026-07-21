"""Generate a machine-readable dump of every registered tool.

Usage:
    uv run python -m percival_weather_mcp.tool_export > docs/tools.json
"""

from __future__ import annotations

import json
import sys

from . import __version__
from .server import register_all_tools, tool_handlers


def build_tools_document() -> dict[str, object]:
    """Return a JSON-serialisable snapshot of every tool."""
    register_all_tools()
    tools: list[dict[str, object]] = []
    for handler in sorted(tool_handlers.values(), key=lambda h: h.name):
        description = handler.get_tool_description()
        tools.append(
            {
                "name": description.name,
                "description": description.description,
                "input_schema": description.inputSchema,
            }
        )
    return {
        "server": "percival-weather-mcp",
        "version": __version__,
        "tool_count": len(tools),
        "tools": tools,
    }


def main() -> None:
    document = build_tools_document()
    json.dump(document, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
