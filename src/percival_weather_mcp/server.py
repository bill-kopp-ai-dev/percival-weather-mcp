"""MCP weather server using FastMCP as the runtime transport layer.

Tool registration is performed through FastMCP's public ``add_tool`` API; each
handler exposes a Pydantic input model and an async ``run`` method that is
registered directly so the JSON schema is derived from Pydantic automatically.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import os
import sys
import time
from typing import Any

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.types import ASGIApp

from .__version__ import __version__
from .config import (
    DEFAULT_AUTH_TOKEN_ENV_VAR,
    DEFAULT_HOST,
    DEFAULT_PORT,
    SERVER_NAME,
    Settings,
    set_settings,
)
from .logging_utils import configure_logging
from .middleware import (
    HealthAndMetricsMiddleware,
    install_security_middleware,
    validate_http_runtime_security,
)
from .observability import track_tool
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

logger = logging.getLogger("percival-weather-mcp")


# ---------------------------------------------------------------------------
# Backward-compatible tool aliases (resolved at dispatch time).
# ---------------------------------------------------------------------------

TOOL_NAME_ALIASES: dict[str, str] = {
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
    return TOOL_NAME_ALIASES.get(name, name)


# ---------------------------------------------------------------------------
# Tool registry.
# ---------------------------------------------------------------------------

tool_handlers: dict[str, ToolHandler] = {}


class WeatherFastMCP(FastMCP):
    """FastMCP subclass that resolves legacy aliases at dispatch time."""

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> Any:
        resolved = resolve_tool_name(name)
        if resolved != name:
            logger.warning("Tool alias used: %s -> %s", name, resolved)
        return await super().call_tool(resolved, arguments)


def _call_handler(handler: ToolHandler, arguments: dict[str, Any]) -> Any:
    """Run ``handler.run_tool`` with metrics instrumentation."""
    with track_tool(handler.name):
        return handler.run_tool(arguments)


def _register_handler_with_fastmcp(mcp_server: FastMCP, handler: ToolHandler) -> None:
    description = (handler.get_tool_description().description or "").strip()

    async def tool_proxy(**kwargs: Any) -> Any:
        normalised = {key: value for key, value in kwargs.items() if value is not None}
        return await _call_handler(handler, normalised)

    tool_proxy.__name__ = f"{handler.name}_proxy"
    tool_proxy.__qualname__ = tool_proxy.__name__
    tool_proxy.__doc__ = description or f"Tool: {handler.name}"

    with contextlib.suppress(Exception):
        mcp_server.remove_tool(handler.name)
    mcp_server.add_tool(
        tool_proxy,
        name=handler.name,
        description=description or None,
    )


def _register_status_tool(mcp_server: FastMCP) -> None:
    async def get_status() -> str:
        return (
            f"Percival Weather MCP Server operational. "
            f"Name: {SERVER_NAME} Version: {__version__}"
        )

    get_status.__name__ = "weather_get_status"
    get_status.__doc__ = "Check the operational status of the weather server."
    with contextlib.suppress(Exception):
        mcp_server.remove_tool("weather_get_status")
    mcp_server.add_tool(get_status, name="weather_get_status", description=get_status.__doc__)


def _sync_fastmcp_tools(mcp_server: FastMCP) -> None:
    for handler in tool_handlers.values():
        _register_handler_with_fastmcp(mcp_server, handler)
    _register_status_tool(mcp_server)


# ---------------------------------------------------------------------------
# Public registration API.
# ---------------------------------------------------------------------------


def add_tool_handler(tool_handler: ToolHandler) -> None:
    """Register a tool handler in the in-memory registry and the FastMCP server."""
    global tool_handlers
    tool_handlers[tool_handler.name] = tool_handler
    if "app" in globals() and app is not None:
        _register_handler_with_fastmcp(app, tool_handler)
    logger.info("Registered tool handler: %s", tool_handler.name)


def get_tool_handler(name: str) -> ToolHandler | None:
    return tool_handlers.get(resolve_tool_name(name))


def register_all_tools() -> None:
    """Register every tool the server knows about."""
    handlers: list[ToolHandler] = [
        GetCurrentWeatherToolHandler(),
        GetWeatherByDateRangeToolHandler(),
        GetWeatherDetailsToolHandler(),
        GetCurrentDateTimeToolHandler(),
        GetTimeZoneInfoToolHandler(),
        ConvertTimeToolHandler(),
        GetAirQualityToolHandler(),
        GetAirQualityDetailsToolHandler(),
    ]
    for handler in handlers:
        add_tool_handler(handler)
    logger.info("Registered %d tool handlers", len(tool_handlers))


# ---------------------------------------------------------------------------
# Server factory and runner.
# ---------------------------------------------------------------------------


_SERVER_STARTED_AT = time.time()


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
    # Make sure the module-level ``app`` reflects the current server so that
    # subsequent ``add_tool_handler`` calls attach to the same instance.
    globals()["app"] = mcp_server
    return mcp_server


def create_starlette_app(mcp_server: FastMCP, *, debug: bool = False) -> Starlette:
    """Return the SSE Starlette app from a FastMCP server."""
    if debug and not mcp_server.settings.debug:
        logger.debug("create_starlette_app(debug=True) called on a non-debug FastMCP instance")
    return mcp_server.sse_app()


def create_streamable_http_app(
    mcp_server: FastMCP,
    *,
    debug: bool = False,
    stateless: bool = False,
) -> Starlette:
    """Return the Streamable HTTP Starlette app from a FastMCP server."""
    if debug and not mcp_server.settings.debug:
        logger.debug("create_streamable_http_app(debug=True) called on a non-debug FastMCP instance")
    if stateless != mcp_server.settings.stateless_http:
        logger.debug(
            "Requested stateless=%s but server is stateless_http=%s",
            stateless,
            mcp_server.settings.stateless_http,
        )
    return mcp_server.streamable_http_app()


def _create_http_transport_app(
    mcp_server: FastMCP,
    *,
    mode: str,
    auth_token: str | None,
    started_at: float,
    version: str,
) -> _ASGIWrapper:
    if mode == "sse":
        http_app = create_starlette_app(mcp_server)
    elif mode == "streamable-http":
        http_app = create_streamable_http_app(mcp_server)
    else:
        raise ValueError(f"Unsupported HTTP mode: {mode}")

    install_security_middleware(http_app, auth_token=auth_token)
    # Health/metrics is wrapped as an outer ASGI middleware so that probes do
    # not hit rate-limit/auth middlewares.
    return _wrap_with_health(http_app, started_at=started_at, version=version)


def _wrap_with_health(app: Starlette, *, started_at: float, version: str) -> _ASGIWrapper:
    """Compose the health/metrics ASGI middleware with the existing Starlette app."""
    return _ASGIWrapper(app, started_at=started_at, version=version)


class _ASGIWrapper:
    """Wraps a Starlette app so health/metrics endpoints bypass auth middleware."""

    def __init__(self, inner: ASGIApp, *, started_at: float, version: str) -> None:
        self._inner = inner
        self._middleware = HealthAndMetricsMiddleware(
            inner, started_at=started_at, version=version
        )

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] == "http" and scope.get("path") in {"/healthz", "/health", "/metrics"}:
            await self._middleware(scope, receive, send)
            return
        await self._inner(scope, receive, send)


async def _run_http_transport(
    mcp_server: FastMCP,
    *,
    mode: str,
    host: str,
    port: int,
    auth_token: str | None,
    ssl_keyfile: str | None,
    ssl_certfile: str | None,
) -> None:
    http_app = _create_http_transport_app(
        mcp_server,
        mode=mode,
        auth_token=auth_token,
        started_at=_SERVER_STARTED_AT,
        version=__version__,
    )
    config = uvicorn.Config(
        http_app,
        host=host,
        port=port,
        log_level="info",
        ssl_keyfile=ssl_keyfile,
        ssl_certfile=ssl_certfile,
    )
    server = uvicorn.Server(config)
    await server.serve()


async def run_server(
    mode: str,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    debug: bool = False,
    stateless: bool = False,
    auth_token: str | None = None,
    allow_remote_http: bool = False,
    auth_token_env: str = DEFAULT_AUTH_TOKEN_ENV_VAR,
    ssl_keyfile: str | None = None,
    ssl_certfile: str | None = None,
) -> None:
    """Unified runner supporting stdio, SSE and streamable-http transports."""
    global app

    set_settings(
        Settings.from_env(
            host=host,
            port=port,
            debug=debug,
            stateless=stateless,
            auth_token=auth_token,
            allow_remote_http=allow_remote_http,
            auth_token_env=auth_token_env,
        )
    )
    configure_logging()

    app = create_fastmcp_server(host=host, port=port, debug=debug, stateless=stateless)

    validate_http_runtime_security(
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
            auth_token=auth_token,
            ssl_keyfile=ssl_keyfile,
            ssl_certfile=ssl_certfile,
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
            auth_token=auth_token,
            ssl_keyfile=ssl_keyfile,
            ssl_certfile=ssl_certfile,
        )
    else:
        raise ValueError(f"Unknown mode: {mode}")


# Module-level server instance used by ``python -m percival_weather_mcp``.
app = create_fastmcp_server()


async def main() -> None:
    """Command-line entry point."""
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
        help="Run in stateless mode (streamable-http only).",
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
    parser.add_argument(
        "--ssl-keyfile",
        default=None,
        help="Path to a PEM-encoded SSL key file (HTTP modes only).",
    )
    parser.add_argument(
        "--ssl-certfile",
        default=None,
        help="Path to a PEM-encoded SSL certificate file (HTTP modes only).",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")

    args = parser.parse_args()
    port = args.port if args.port is not None else int(os.environ.get("PORT", DEFAULT_PORT))
    auth_token = os.environ.get(args.auth_token_env, "").strip() or None

    configure_logging()
    register_all_tools()
    logger.info("Starting MCP Weather Server in %s mode...", args.mode)
    logger.info("Python version: %s", sys.version)
    logger.info("Registered tools: %s", sorted(tool_handlers.keys()))

    await run_server(
        args.mode,
        args.host,
        port,
        args.debug,
        args.stateless,
        auth_token=auth_token,
        allow_remote_http=args.allow_remote_http,
        auth_token_env=args.auth_token_env,
        ssl_keyfile=args.ssl_keyfile,
        ssl_certfile=args.ssl_certfile,
    )


if __name__ == "__main__":
    asyncio.run(main())
