"""MCP weather server using FastMCP as the runtime transport layer.

Tool registration is performed through FastMCP's public ``add_tool`` API; each
handler exposes a Pydantic input model and an async ``run`` method that is
registered directly so the JSON schema is derived from Pydantic automatically.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import inspect
import logging
import os
import sys
import time
from collections.abc import Callable
from typing import Any

import uvicorn
from mcp.server.fastmcp import FastMCP
from pydantic.fields import FieldInfo
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
from .observability import track_tool_async
from .prompts import register_prompts
from .resources import register_resources
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


async def _call_handler(handler: ToolHandler, arguments: dict[str, Any]) -> Any:
    """Run ``handler.run_tool`` with metrics instrumentation.

    The coroutine is awaited **inside** the metric context so latency reflects
    the real execution time and exceptions bubble up to the metric counters.
    """
    async with track_tool_async(handler.name):
        return await handler.run_tool(arguments)


def _register_handler_with_fastmcp(mcp_server: FastMCP, handler: ToolHandler) -> None:
    description = (handler.get_tool_description().description or "").strip()

    tool_proxy = _make_tool_proxy(handler)

    with contextlib.suppress(Exception):
        mcp_server.remove_tool(handler.name)
    mcp_server.add_tool(
        tool_proxy,
        name=handler.name,
        description=description or None,
    )


def _make_tool_proxy(handler: ToolHandler) -> Callable[..., Any]:
    """Build an MCP-compatible proxy function for ``handler``.

    FastMCP derives the ``inputSchema`` of every registered tool from the
    signature of the callable passed to ``add_tool`` — using ``func_metadata``
    under the hood. A plain ``async def ...(**kwargs)`` therefore produces a
    schema with a single ``kwargs`` field, which is exactly the bug described
    in ``MCP_Docs/Issues/2026-07-21-percival-weather-mcp-broken-input-schema.md``.

    To expose the real per-field schema we reconstruct an
    ``inspect.Signature`` whose parameters mirror the fields declared on the
    handler's ``input_model`` (a Pydantic ``BaseModel``). FastMCP then introspects
    the rebuilt signature and builds a correct schema, while the underlying
    function still receives the original kwargs dict that ``_call_handler``
    forwards to ``handler.run_tool``.
    """
    description = (handler.get_tool_description().description or "").strip()

    async def tool_proxy(**kwargs: Any) -> Any:
        # Drop keys that arrived as ``None`` so the handler's Pydantic model can
        # apply its real defaults instead of being forced to validate ``None``.
        normalised = {key: value for key, value in kwargs.items() if value is not None}
        return await _call_handler(handler, normalised)

    input_model_cls = getattr(handler.__class__, "input_model", None)
    if input_model_cls is None or not isinstance(input_model_cls, type):
        # Fallback for legacy handlers: keep the original **kwargs behaviour.
        tool_proxy.__name__ = f"{handler.name}_proxy"
        tool_proxy.__qualname__ = tool_proxy.__name__
        tool_proxy.__doc__ = description or f"Tool: {handler.name}"
        return tool_proxy

    model_fields = getattr(input_model_cls, "model_fields", {}) or {}

    annotations: dict[str, Any] = {}
    parameters: list[inspect.Parameter] = []
    empty = inspect.Parameter.empty
    for field_name, field_info in model_fields.items():
        annotation = field_info.annotation if field_info.annotation is not empty else Any
        annotations[field_name] = annotation
        default: Any
        if field_info.is_required():
            default = empty
        else:
            default = field_info.default if field_info.default is not empty else FieldInfo.from_field().default
        parameters.append(
            inspect.Parameter(
                name=field_name,
                kind=inspect.Parameter.KEYWORD_ONLY,
                annotation=annotation,
                default=default,
            )
        )

    if parameters:
        # Force a KEYWORD_ONLY-only signature. FastMCP's func_metadata expects
        # real parameter names, so this is mandatory.
        rebuilt_sig = inspect.Signature(
            parameters=parameters,
            return_annotation=inspect.Signature.empty,
        )
        tool_proxy.__signature__ = rebuilt_sig  # type: ignore[attr-defined]

    # ``__annotations__`` is the primary source for ``func_metadata``'s
    # ``_get_typed_signature``; update it to match the fields we just added.
    tool_proxy.__annotations__ = annotations
    tool_proxy.__name__ = f"{handler.name}_proxy"
    tool_proxy.__qualname__ = tool_proxy.__name__
    tool_proxy.__doc__ = description or f"Tool: {handler.name}"

    return tool_proxy


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
    register_prompts(mcp_server)
    register_resources(mcp_server)


# ---------------------------------------------------------------------------
# Public registration API.
# ---------------------------------------------------------------------------


def add_tool_handler(tool_handler: ToolHandler) -> None:
    """Register a tool handler in the in-memory registry.

    The handler is also attached to the module-level ``app`` server when one
    exists, so the CLI bootstrap can call this function before the server is
    actually started.
    """
    global tool_handlers
    tool_handlers[tool_handler.name] = tool_handler
    if "app" in globals() and globals()["app"] is not None:
        _register_handler_with_fastmcp(globals()["app"], tool_handler)
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
    """Create a fresh, configured FastMCP server instance.

    Each call returns a new ``WeatherFastMCP`` object — the module-level
    ``app`` is NOT mutated here so that callers (tests, ``tool_export``,
    CLI bootstrap) get independent instances and don't share registration
    state.
    """
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

    # Build (or reuse) the server instance. ``app`` is None until ``main``
    # initialises it; if a caller invokes ``run_server`` directly without
    # going through ``main`` we create a fresh instance here.
    if app is None:
        globals()["app"] = create_fastmcp_server(
            host=host, port=port, debug=debug, stateless=stateless
        )
    server_instance = app
    assert server_instance is not None  # for type checkers

    validate_http_runtime_security(
        mode=mode,
        host=host,
        allow_remote_http=allow_remote_http,
        auth_token=auth_token,
        auth_token_env=auth_token_env,
    )

    if mode == "stdio":
        logger.info("Starting stdio server...")
        await server_instance.run_stdio_async()
    elif mode == "sse":
        logger.info("Starting SSE server on %s:%s...", host, port)
        await _run_http_transport(
            server_instance,
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
            server_instance,
            mode="streamable-http",
            host=host,
            port=port,
            auth_token=auth_token,
            ssl_keyfile=ssl_keyfile,
            ssl_certfile=ssl_certfile,
        )
    else:
        raise ValueError(f"Unknown mode: {mode}")


# Module-level server instance placeholder. Populated by :func:`main` when the
# CLI bootstrap runs; stays ``None`` for callers that want a fresh instance
# via :func:`create_fastmcp_server` (e.g. tests, ``tool_export``).
app: WeatherFastMCP | None = None


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
    # Materialise the module-level ``app`` so tools are addressable as
    # ``percival_weather_mcp.server.app`` for the lifetime of this process.
    globals()["app"] = create_fastmcp_server(
        host=args.host,
        port=port,
        debug=args.debug,
        stateless=args.stateless,
    )
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
