"""
MCP weather server using FastMCP as the runtime transport layer.
Tool handlers remain modular, while transport registration is done entirely
through FastMCP public APIs.
"""

import argparse
import asyncio
import hmac
import inspect
import logging
import os
import sys
from collections.abc import Sequence
from ipaddress import ip_address
from typing import Annotated, Any, Dict, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import EmbeddedResource, ImageContent, TextContent, Tool
from pydantic import Field
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
import uvicorn

from .tools.toolhandler import ToolHandler
from .tools.tools_air_quality import (
    GetAirQualityDetailsToolHandler,
    GetAirQualityToolHandler,
)
from .tools.tools_time import (
    ConvertTimeToolHandler,
    GetCurrentDateTimeToolHandler,
    GetTimeZoneInfoToolHandler,
)
from .tools.tools_weather import (
    GetCurrentWeatherToolHandler,
    GetWeatherByDateRangeToolHandler,
    GetWeatherDetailsToolHandler,
)


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("percival-weather-mcp")

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080
DEFAULT_AUTH_TOKEN_ENV_VAR = "MCP_WEATHER_AUTH_TOKEN"
SERVER_NAME = "percival-weather-mcp"

# Global tool handlers registry
tool_handlers: Dict[str, ToolHandler] = {}

# Backward-compatible tool aliases
TOOL_NAME_ALIASES: Dict[str, str] = {
    "get_weather_byDateTimeRange": "weather_get_by_range",
    "get_weather_by_datetime_range": "weather_get_by_range",
    "get_current_weather": "weather_get_current",
    "get_weather_details": "weather_get_details",
    "get_current_datetime": "weather_get_time",
    "get_timezone_info": "weather_get_timezone",
    "convert_time": "weather_convert_time",
    "get_air_quality": "weather_get_air_quality",
    "get_air_quality_details": "weather_get_air_quality_details",
}


def resolve_tool_name(name: str) -> str:
    """Resolve legacy aliases to canonical tool names."""
    return TOOL_NAME_ALIASES.get(name, name)


class WeatherFastMCP(FastMCP):
    """FastMCP subclass that resolves legacy aliases at dispatch time."""

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        resolved_name = resolve_tool_name(name)
        if resolved_name != name:
            logger.warning("Tool alias used: %s -> %s", name, resolved_name)
        return await super().call_tool(resolved_name, arguments)


class BearerTokenAuthMiddleware(BaseHTTPMiddleware):
    """Require a shared bearer token for HTTP requests."""

    def __init__(self, app, token: str):
        super().__init__(app)
        self._token = token.strip()

    async def dispatch(self, request: Request, call_next):
        authorization = request.headers.get("authorization", "")
        header_token = request.headers.get("x-mcp-auth-token", "")

        provided_token = ""
        if authorization.lower().startswith("bearer "):
            provided_token = authorization[7:].strip()
        elif header_token:
            provided_token = header_token.strip()

        if not provided_token or not hmac.compare_digest(provided_token, self._token):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        return await call_next(request)


def _is_loopback_host(host: str) -> bool:
    normalized_host = host.strip().lower()
    if normalized_host in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        return ip_address(normalized_host).is_loopback
    except ValueError:
        return False


def _validate_http_runtime_security(
    *,
    mode: str,
    host: str,
    allow_remote_http: bool,
    auth_token: str | None,
    auth_token_env: str,
) -> None:
    if mode not in {"sse", "streamable-http"}:
        return

    loopback_host = _is_loopback_host(host)
    if not loopback_host and not allow_remote_http:
        raise ValueError(
            "Refusing to bind HTTP transport to a non-loopback host without --allow-remote-http."
        )

    if not loopback_host and not auth_token:
        raise ValueError(
            "Remote HTTP mode requires authentication. "
            f"Set {auth_token_env} or choose a different token env var with --auth-token-env."
        )

    if loopback_host and not auth_token:
        logger.warning(
            "Starting HTTP mode on loopback host without authentication token. "
            "This is acceptable for local development only."
        )


def _create_http_transport_app(
    mcp_server: FastMCP,
    *,
    mode: str,
    stateless: bool,
    auth_token: str | None,
) -> Starlette:
    if mode == "sse":
        http_app = create_starlette_app(mcp_server)
    elif mode == "streamable-http":
        http_app = create_streamable_http_app(mcp_server, stateless=stateless)
    else:
        raise ValueError(f"Unsupported HTTP mode: {mode}")

    if auth_token:
        http_app.add_middleware(BearerTokenAuthMiddleware, token=auth_token)

    return http_app


async def _run_http_transport(
    mcp_server: FastMCP,
    *,
    mode: str,
    host: str,
    port: int,
    stateless: bool,
    auth_token: str | None,
) -> None:
    http_app = _create_http_transport_app(
        mcp_server,
        mode=mode,
        stateless=stateless,
        auth_token=auth_token,
    )
    config = uvicorn.Config(http_app, host=host, port=port, log_level="info")
    uvicorn_server = uvicorn.Server(config)
    await uvicorn_server.serve()


def _schema_to_annotation(schema: dict[str, Any]) -> Any:
    """
    Convert a subset of JSON Schema types used by tool input schemas into Python
    annotations that FastMCP can translate back into tool schemas.
    """
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        non_null_types = [candidate for candidate in schema_type if candidate != "null"]
        schema_type = non_null_types[0] if non_null_types else "null"

    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and enum_values:
        return Literal.__getitem__(tuple(enum_values))

    if schema_type == "string":
        return str
    if schema_type == "integer":
        return int
    if schema_type == "number":
        return float
    if schema_type == "boolean":
        return bool
    if schema_type == "null":
        return type(None)

    if schema_type == "array":
        items_schema = schema.get("items", {})
        if isinstance(items_schema, dict):
            item_annotation = _schema_to_annotation(items_schema)
        else:
            item_annotation = Any
        return list[item_annotation]

    if schema_type == "object":
        return dict[str, Any]

    return Any


def _build_tool_docstring(tool_description: Tool) -> str:
    """
    Build a rich docstring for FastMCP tool proxies from MCP Tool metadata.

    The resulting docstring is what many MCP clients surface to AI agents.
    """
    input_schema = tool_description.inputSchema or {}
    properties = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))

    lines: list[str] = []
    base_description = (tool_description.description or "").strip()
    if base_description:
        lines.append(base_description)
    else:
        lines.append(f"Tool: {tool_description.name}")

    if isinstance(properties, dict) and properties:
        lines.append("")
        lines.append("Args:")
        for argument_name, raw_property_schema in properties.items():
            property_schema = raw_property_schema if isinstance(raw_property_schema, dict) else {}

            schema_type = property_schema.get("type", "any")
            if isinstance(schema_type, list):
                schema_type = " | ".join(str(candidate) for candidate in schema_type)

            requirement = "required" if argument_name in required else "optional"
            argument_description = str(property_schema.get("description", "")).strip()
            default_suffix = ""
            if argument_name not in required and "default" in property_schema:
                default_suffix = f" Default: {property_schema.get('default')!r}."

            details = argument_description or "No description provided."
            lines.append(
                f"  {argument_name} ({schema_type}; {requirement}): {details}{default_suffix}"
            )

    lines.append("")
    lines.append("Returns:")
    lines.append("  MCP content sequence (typically one TextContent item).")
    return "\n".join(lines)


def _build_fastmcp_callable(tool_handler: ToolHandler, tool_description: Tool):
    """
    Build a callable with a dynamic signature from Tool.inputSchema.
    This preserves the existing handler implementation while using FastMCP's
    public add_tool API for registration.
    """
    input_schema = tool_description.inputSchema or {}
    properties = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))

    parameters: list[inspect.Parameter] = []
    annotations: dict[str, Any] = {}

    if isinstance(properties, dict):
        for argument_name, raw_property_schema in properties.items():
            property_schema = raw_property_schema if isinstance(raw_property_schema, dict) else {}
            argument_annotation = _schema_to_annotation(property_schema)

            argument_description = property_schema.get("description")
            if isinstance(argument_description, str) and argument_description.strip():
                argument_annotation = Annotated[
                    argument_annotation,
                    Field(description=argument_description.strip()),
                ]

            if argument_name in required:
                default_value = inspect.Parameter.empty
            else:
                default_value = property_schema.get("default", None)

            parameters.append(
                inspect.Parameter(
                    name=argument_name,
                    kind=inspect.Parameter.KEYWORD_ONLY,
                    default=default_value,
                    annotation=argument_annotation,
                )
            )
            annotations[argument_name] = argument_annotation

    signature = inspect.Signature(parameters=parameters)

    async def fastmcp_tool_proxy(**kwargs):
        # Preserve legacy behavior for optional fields omitted by callers.
        normalized_args = {key: value for key, value in kwargs.items() if value is not None}
        return await tool_handler.run_tool(normalized_args)

    fastmcp_tool_proxy.__name__ = f"{tool_handler.name}_proxy"
    fastmcp_tool_proxy.__qualname__ = fastmcp_tool_proxy.__name__
    fastmcp_tool_proxy.__doc__ = _build_tool_docstring(tool_description)
    fastmcp_tool_proxy.__signature__ = signature  # type: ignore[attr-defined]
    annotations["return"] = Sequence[TextContent | ImageContent | EmbeddedResource]
    fastmcp_tool_proxy.__annotations__ = annotations
    return fastmcp_tool_proxy


def _register_handler_with_fastmcp(mcp_server: FastMCP, tool_handler: ToolHandler) -> None:
    tool_description = tool_handler.get_tool_description()
    tool_callable = _build_fastmcp_callable(tool_handler, tool_description)

    try:
        mcp_server.remove_tool(tool_description.name)
    except Exception:
        # Tool may not exist yet; safe to continue.
        pass

    mcp_server.add_tool(
        tool_callable,
        name=tool_description.name,
        description=tool_description.description,
    )


def _sync_fastmcp_tools(mcp_server: FastMCP) -> None:
    """Register all current ToolHandler instances in the given FastMCP server."""
    for handler in tool_handlers.values():
        _register_handler_with_fastmcp(mcp_server, handler)


def add_tool_handler(tool_handler: ToolHandler) -> None:
    """
    Register a tool handler in the in-memory handler registry.

    Args:
        tool_handler: The tool handler instance to register.
    """
    global tool_handlers
    if "app" in globals():
        _register_handler_with_fastmcp(app, tool_handler)
    tool_handlers[tool_handler.name] = tool_handler
    logger.info("Registered tool handler: %s", tool_handler.name)


def get_tool_handler(name: str) -> ToolHandler | None:
    """
    Retrieve a tool handler by name.

    Args:
        name: The name of the tool handler.

    Returns:
        The tool handler instance or None if not found.
    """
    return tool_handlers.get(resolve_tool_name(name))


def register_all_tools() -> None:
    """
    Register all available tool handlers.

    This function serves as the central registry for all tools.
    New tool handlers should be added here for automatic registration.
    """
    add_tool_handler(GetCurrentWeatherToolHandler())
    add_tool_handler(GetWeatherByDateRangeToolHandler())
    add_tool_handler(GetWeatherDetailsToolHandler())

    add_tool_handler(GetCurrentDateTimeToolHandler())
    add_tool_handler(GetTimeZoneInfoToolHandler())
    add_tool_handler(ConvertTimeToolHandler())

    add_tool_handler(GetAirQualityToolHandler())
    add_tool_handler(GetAirQualityDetailsToolHandler())

    logger.info("Registered %d tool handlers", len(tool_handlers))


def reset_tool_registry() -> None:
    """
    Reset in-memory tool handlers and recreate the FastMCP instance with no tools.
    Useful for tests that require clean tool registration state.
    """
    global app
    tool_handlers.clear()

    if "app" in globals():
        host = app.settings.host
        port = app.settings.port
        debug = app.settings.debug
        stateless = app.settings.stateless_http
    else:
        host = DEFAULT_HOST
        port = DEFAULT_PORT
        debug = False
        stateless = False

    app = create_fastmcp_server(
        host=host,
        port=port,
        debug=debug,
        stateless=stateless,
    )


def create_fastmcp_server(
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    debug: bool = False,
    stateless: bool = False,
) -> WeatherFastMCP:
    """Create a configured FastMCP server instance."""
    mcp_server = WeatherFastMCP(
        name=SERVER_NAME,
        host=host,
        port=port,
        debug=debug,
        sse_path="/sse",
        message_path="/messages/",
        streamable_http_path="/mcp",
        stateless_http=stateless,
    )

    if tool_handlers:
        _sync_fastmcp_tools(mcp_server)

    return mcp_server


def create_starlette_app(mcp_server: FastMCP, *, debug: bool = False) -> Starlette:
    """
    Return an SSE Starlette app from a FastMCP server.
    Kept for compatibility with previous module API.
    """
    if debug and not mcp_server.settings.debug:
        logger.debug("create_starlette_app(debug=True) called on a non-debug FastMCP instance")
    return mcp_server.sse_app()


def create_streamable_http_app(
    mcp_server: FastMCP,
    *,
    debug: bool = False,
    stateless: bool = False,
) -> Starlette:
    """
    Return a Streamable HTTP Starlette app from a FastMCP server.
    Kept for compatibility with previous module API.
    """
    if debug and not mcp_server.settings.debug:
        logger.debug("create_streamable_http_app(debug=True) called on a non-debug FastMCP instance")
    if stateless != mcp_server.settings.stateless_http:
        logger.debug(
            "Requested stateless=%s but server is stateless_http=%s",
            stateless,
            mcp_server.settings.stateless_http,
        )
    return mcp_server.streamable_http_app()


# Module-level server for compatibility with code that imports `app`.
app = create_fastmcp_server()


async def run_server(
    mode: str,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    debug: bool = False,
    stateless: bool = False,
    auth_token: str | None = None,
    allow_remote_http: bool = False,
    auth_token_env: str = DEFAULT_AUTH_TOKEN_ENV_VAR,
) -> None:
    """
    Unified server runner that supports stdio, SSE, and streamable-http modes.

    Args:
        mode: Server mode ("stdio", "sse", or "streamable-http")
        host: Host to bind to (HTTP modes only)
        port: Port to listen on (HTTP modes only)
        debug: Whether to enable debug mode
        stateless: Whether to use stateless mode (streamable-http only)
        auth_token: Optional shared token for HTTP authentication
        allow_remote_http: Whether to allow non-loopback host binding
        auth_token_env: Environment variable name used for auth token lookup
    """
    global app
    app = create_fastmcp_server(host=host, port=port, debug=debug, stateless=stateless)

    _validate_http_runtime_security(
        mode=mode,
        host=host,
        allow_remote_http=allow_remote_http,
        auth_token=auth_token,
        auth_token_env=auth_token_env,
    )

    if mode == "stdio":
        logger.info("Starting stdio server...")
        await app.run_stdio_async()
    elif mode == "sse":
        logger.info("Starting SSE server on %s:%s...", host, port)
        await _run_http_transport(
            app,
            mode="sse",
            host=host,
            port=port,
            stateless=False,
            auth_token=auth_token,
        )
    elif mode == "streamable-http":
        mode_desc = "stateless" if stateless else "stateful"
        logger.info("Starting Streamable HTTP server (%s) on %s:%s...", mode_desc, host, port)
        logger.info("Endpoint: http://%s:%s/mcp", host, port)
        await _run_http_transport(
            app,
            mode="streamable-http",
            host=host,
            port=port,
            stateless=stateless,
            auth_token=auth_token,
        )
    else:
        raise ValueError(f"Unknown mode: {mode}")


@app.tool("weather_get_status")
def get_status() -> str:
    """Check the operational status of the weather server."""
    return f"Percival Weather MCP Server operational. Name: {SERVER_NAME}"


async def main() -> None:
    """
    Main entry point for the MCP weather server.
    Supports stdio, SSE, and streamable-http modes based on command line arguments.
    For Smithery deployments, reads PORT from environment variable.
    """
    parser = argparse.ArgumentParser(
        description="MCP Weather Server - supports stdio, SSE, and streamable-http modes"
    )
    parser.add_argument(
        "--mode",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="Server mode: stdio (default), sse, or streamable-http",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"Host to bind to (HTTP modes only, default: {DEFAULT_HOST})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to listen on (HTTP modes only, default: from PORT env var or 8080)",
    )
    parser.add_argument(
        "--stateless",
        action="store_true",
        help="Run in stateless mode (streamable-http only, creates fresh transport per request)",
    )
    parser.add_argument(
        "--allow-remote-http",
        action="store_true",
        help="Allow binding HTTP transports to non-loopback hosts.",
    )
    parser.add_argument(
        "--auth-token-env",
        default=DEFAULT_AUTH_TOKEN_ENV_VAR,
        help=(
            "Environment variable name that stores the shared HTTP auth token "
            f"(default: {DEFAULT_AUTH_TOKEN_ENV_VAR})."
        ),
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")

    args = parser.parse_args()
    port = args.port if args.port is not None else int(os.environ.get("PORT", DEFAULT_PORT))
    auth_token = os.environ.get(args.auth_token_env, "").strip() or None

    try:
        register_all_tools()
        logger.info("Starting MCP Weather Server in %s mode...", args.mode)
        logger.info("Python version: %s", sys.version)
        logger.info("Registered tools: %s", list(tool_handlers.keys()))
        await run_server(
            args.mode,
            args.host,
            port,
            args.debug,
            args.stateless,
            auth_token=auth_token,
            allow_remote_http=args.allow_remote_http,
            auth_token_env=args.auth_token_env,
        )
    except Exception as e:
        logger.exception("Failed to start server: %s", str(e))
        raise


if __name__ == "__main__":
    asyncio.run(main())
