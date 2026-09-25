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


def _primitive_type(schema: object) -> tuple[str, dict[str, str] | None]:
    """Resolve a JSON Schema node to the registry-friendly ``(type, items)`` pair.

    The Docker MCP registry restricts argument types to ``string | number |
    integer | boolean | array``. Pydantic emits ``anyOf`` for ``Optional[X]``
    and may emit ``type: [\"X\", \"null\"]``; this helper unwraps both.
    """
    if not isinstance(schema, dict):
        return "string", None
    if "anyOf" in schema:
        for branch in schema["anyOf"]:
            inner_type, inner_items = _primitive_type(branch)
            if inner_type != "null":
                return inner_type, inner_items
        return "string", None
    type_value = schema.get("type")
    if isinstance(type_value, list):
        for branch in type_value:
            if branch != "null":
                type_value = branch
                break
    if type_value == "array":
        items = schema.get("items") or {}
        inner_type = items.get("type", "string") if isinstance(items, dict) else "string"
        if isinstance(inner_type, list):
            inner_type = next((b for b in inner_type if b != "null"), "string")
        return "array", {"type": inner_type}
    if type_value in {"string", "number", "integer", "boolean"}:
        return type_value, None
    return "string", None


def _collect_registry_arguments(schema: object) -> list[dict[str, object]]:
    """Map a Pydantic ``model_json_schema`` to the registry argument layout."""
    if not isinstance(schema, dict):
        return []
    properties = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    arguments: list[dict[str, object]] = []
    for arg_name, arg_schema in properties.items():
        arg_type, items = _primitive_type(arg_schema)
        description = ""
        if isinstance(arg_schema, dict):
            description = arg_schema.get("description") or arg_schema.get("title") or ""
        entry: dict[str, object] = {
            "name": arg_name,
            "type": arg_type,
            "desc": description,
            "optional": arg_name not in required,
        }
        if items is not None:
            entry["items"] = items
        arguments.append(entry)
    return arguments


def build_registry_tools_document() -> dict[str, object]:
    """Build the ``tools.json`` payload consumed by the Docker MCP registry.

    Unlike :func:`build_primitives_document` (which preserves the full Pydantic
    JSON schema for ``docs/tools.json``), this layout matches the restricted
    schema accepted by the registry's task wizard:

    * ``type`` is one of ``string | number | integer | boolean | array``.
    * ``Optional[list[X]]`` collapses to ``type: array, items: {type: X}``.
    * ``optional`` is a boolean derived from the Pydantic ``required`` list.

    The return value is an object with the list under ``tools`` so callers
    can introspect the server/version metadata alongside the tool list.
    The CLI helper (:func:`registry_main`) writes only the ``tools`` array
    to disk, which is the file format the registry task wizard consumes.
    """
    primitives = build_primitives_document()
    raw_tools = primitives.get("tools")
    if not isinstance(raw_tools, list):
        raw_tools = []
    tools: list[dict[str, object]] = []
    for tool in raw_tools:
        if not isinstance(tool, dict):
            continue
        tools.append(
            {
                "name": tool.get("name", ""),
                "description": tool.get("description", ""),
                "arguments": _collect_registry_arguments(tool.get("input_schema")),
            }
        )
    return {
        "server": primitives.get("server", "percival-weather-mcp"),
        "version": primitives.get("version", __version__),
        "tools": tools,
    }


def registry_tools_array() -> list[dict[str, object]]:
    """Return only the registry-shaped tool array (drops server/version)."""
    document = build_registry_tools_document()
    tools = document.get("tools")
    if not isinstance(tools, list):
        return []
    return tools


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


def registry_main() -> None:
    """CLI helper that emits the Docker MCP registry ``tools.json`` payload.

    Writes a JSON array (not an object) so the file is directly accepted by
    the registry's task wizard.
    """
    document = registry_tools_array()
    json.dump(document, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--registry":
        registry_main()
    else:
        main()
