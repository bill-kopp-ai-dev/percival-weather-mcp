"""Generate a machine-readable dump of every primitive exposed by the server.

Usage:
    uv run python -m percival_weather_mcp.tool_export > docs/tools.json
"""

from __future__ import annotations

import json
import sys

from . import __version__
from .prompts import register_prompts
from .resources import register_resources
from .server import (
    STATUS_TOOL_DESCRIPTION,
    STATUS_TOOL_NAME,
    FastMCP,
    create_fastmcp_server,
    register_all_tools,
    tool_handlers,
)


def _dump_tools() -> list[dict[str, object]]:
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
    tools.append(
        {
            "name": STATUS_TOOL_NAME,
            "description": STATUS_TOOL_DESCRIPTION,
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        }
    )
    return tools


def _dump_prompts(mcp_server: FastMCP) -> list[dict[str, object]]:
    prompts: list[dict[str, object]] = []
    for prompt in sorted(mcp_server._prompt_manager.list_prompts(), key=lambda p: p.name):
        prompts.append(
            {
                "name": prompt.name,
                "description": prompt.description,
                "arguments": [
                    {
                        "name": arg.name,
                        "description": arg.description,
                        "required": arg.required,
                    }
                    for arg in (prompt.arguments or [])
                ],
            }
        )
    return prompts


def _dump_resources(mcp_server: FastMCP) -> list[dict[str, object]]:
    resources: list[dict[str, object]] = []
    for resource in sorted(mcp_server._resource_manager.list_resources(), key=lambda r: str(r.uri)):
        resources.append(
            {
                "uri": str(resource.uri),
                "name": resource.name,
                "description": resource.description,
                "mime_type": resource.mime_type,
            }
        )
    return resources


def _dump_resource_templates(mcp_server: FastMCP) -> list[dict[str, object]]:
    templates: list[dict[str, object]] = []
    for template in sorted(
        mcp_server._resource_manager.list_templates(),
        key=lambda t: str(t.uri_template),
    ):
        templates.append(
            {
                "uri_template": str(template.uri_template),
                "name": template.name,
                "description": template.description,
            }
        )
    return templates


def build_primitives_document() -> dict[str, object]:
    """Return a JSON-serialisable snapshot of every primitive exposed by the server."""
    mcp_server = create_fastmcp_server()
    register_all_tools()
    register_prompts(mcp_server)
    register_resources(mcp_server)
    return {
        "server": "percival-weather-mcp",
        "version": __version__,
        "tools": _dump_tools(),
        "prompts": _dump_prompts(mcp_server),
        "resources": _dump_resources(mcp_server),
        "resource_templates": _dump_resource_templates(mcp_server),
    }


def build_tools_document() -> dict[str, object]:
    """Backward-compatible alias used by older scripts."""
    document = build_primitives_document()
    tools = document["tools"]
    if not isinstance(tools, list):
        msg = "tools must be a list"
        raise TypeError(msg)
    return {
        "server": document["server"],
        "version": document["version"],
        "tool_count": len(tools),
        "tools": tools,
    }


def main() -> None:
    document = build_primitives_document()
    json.dump(document, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
