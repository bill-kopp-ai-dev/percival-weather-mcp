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
import signal
import sys
import time
from collections.abc import Callable, Iterable
from typing import Any

import uvicorn
from mcp import McpError
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ResourceError
from mcp.types import INVALID_PARAMS, ErrorData
from pydantic import AnyUrl
from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from .__version__ import __version__
from .config import (
    DEFAULT_AUTH_TOKEN_ENV_VAR,
    DEFAULT_HOST,
    DEFAULT_PORT,
    SERVER_NAME,
    ConfigurationError,
    Settings,
    read_port,
    set_settings,
)
from .logging_utils import configure_logging
from .middleware import (
    HealthAndMetricsMiddleware,
    bearer_token_from_headers,
    bearer_token_matches,
    install_security_middleware,
    scope_headers,
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


STATUS_TOOL_NAME = "weather_get_status"
STATUS_TOOL_DESCRIPTION = "Check the operational status of the weather server."

#: JSON-RPC error code for "resource not found", from the MCP standard error
#: codes. The SDK does not export a constant for it.
RESOURCE_NOT_FOUND = -32002

#: Conventional exit status for a process interrupted by a signal (128 + signum).
SIGINT_EXIT_CODE = 130
SIGTERM_EXIT_CODE = 143

#: Prefix the SDK adds when a resource template fails to build its resource.
_SDK_TEMPLATE_ERROR_PREFIX = "Error creating resource from template: "


def _strip_sdk_template_prefix(message: str) -> str:
    """Remove the SDK's template-error prefix from ``message``.

    The SDK wraps the template failure twice (once in the template, once in
    the resource manager), so the prefix is removed while it is present.
    """
    while message.startswith(_SDK_TEMPLATE_ERROR_PREFIX):
        message = message[len(_SDK_TEMPLATE_ERROR_PREFIX) :]
    return message


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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._publish_product_version()

    def _publish_product_version(self) -> None:
        """Advertise the *product* version in ``serverInfo`` (F-008).

        FastMCP does not forward a version to the low-level MCP server, so
        ``create_initialization_options()`` falls back to the **SDK** version
        (``pkg_version("mcp")``). The handshake then reports e.g. ``1.30.0``
        for a product whose version is ``0.9.0`` — and the gateway, or any
        consumer that identifies the server by the handshake version, sees the
        wrong number.
        """
        low_level = getattr(self, "_mcp_server", None)
        if low_level is None:  # pragma: no cover - depends on SDK internals
            logger.warning("Could not publish the product version: unexpected FastMCP internals.")
            return
        low_level.version = __version__

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        resolved = resolve_tool_name(name)
        if resolved != name:
            logger.warning("Tool alias used: %s -> %s", name, resolved)
        return await super().call_tool(resolved, arguments)

    async def get_prompt(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Render a prompt, mapping a validation failure to a wire-level error.

        FastMCP re-raises every failure as a bare ``ValueError``, which the
        low-level server converts into a JSON-RPC error with code ``0`` — not a
        standard JSON-RPC code, and indistinguishable from an internal failure.
        A missing required argument is an *invalid params* condition, so it is
        reported as such (-32602).
        """
        prompt = self._prompt_manager.get_prompt(name)
        if prompt is None:
            raise McpError(ErrorData(code=INVALID_PARAMS, message=f"Unknown prompt: {name}"))
        required = {arg.name for arg in (prompt.arguments or []) if arg.required}
        missing = required - set(arguments or {})
        if missing:
            raise McpError(
                ErrorData(
                    code=INVALID_PARAMS,
                    message=f"Missing required arguments: {', '.join(sorted(missing))}",
                )
            )
        return await super().get_prompt(name, arguments)

    async def read_resource(self, uri: AnyUrl | str) -> Iterable[Any]:
        """Read a resource, mapping a missing resource to a wire-level error.

        The template ``weather://schema/{tool_name}`` used to answer with a
        **successful** read whose payload was ``{"error": "unknown tool ..."}``.
        An agent that trusts a successful read would show that JSON to the
        user as if it were the schema. The template now raises, and this
        override turns the failure into the JSON-RPC error the MCP schema
        defines for a resource that does not exist.
        """
        try:
            return await super().read_resource(uri)
        except (ResourceError, ValueError) as exc:
            message = _strip_sdk_template_prefix(str(exc))
            raise McpError(ErrorData(code=RESOURCE_NOT_FOUND, message=message)) from exc


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
        elif field_info.default_factory is not None:
            # ``field_info.default`` is ``PydanticUndefined`` when only a
            # ``default_factory`` is declared; calling the factory produces the
            # real value to surface in the rebuilt signature.
            default = field_info.default_factory()
        else:
            default = field_info.default
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
            f"Percival Weather MCP Server operational. Name: {SERVER_NAME} Version: {__version__}"
        )

    get_status.__name__ = STATUS_TOOL_NAME
    get_status.__doc__ = STATUS_TOOL_DESCRIPTION
    with contextlib.suppress(Exception):
        mcp_server.remove_tool(STATUS_TOOL_NAME)
    mcp_server.add_tool(get_status, name=STATUS_TOOL_NAME, description=STATUS_TOOL_DESCRIPTION)


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
        logger.debug(
            "create_streamable_http_app(debug=True) called on a non-debug FastMCP instance"
        )
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
    # not hit rate-limit/auth middlewares. ``/metrics`` is the exception: it
    # carries operational counters, so it requires the bearer token whenever
    # one is configured (A-011).
    return _wrap_with_health(
        http_app, started_at=started_at, version=version, metrics_token=auth_token
    )


def _wrap_with_health(
    app: Starlette,
    *,
    started_at: float,
    version: str,
    metrics_token: str | None = None,
) -> _ASGIWrapper:
    """Compose the health/metrics ASGI middleware with the existing Starlette app."""
    return _ASGIWrapper(app, started_at=started_at, version=version, metrics_token=metrics_token)


class _ASGIWrapper:
    """Serves the health probes outside the auth middleware; ``/metrics`` needs the token.

    ``/healthz`` and ``/health`` stay open: they are liveness probes used by
    orchestrators that do not hold the bearer token, and they expose nothing
    beyond the server name, version and uptime.

    ``/metrics`` used to be open as well. It carries operational counters
    (tool calls, upstream requests and errors), so it now requires the same
    bearer token as the rest of the HTTP surface — but only when a token is
    configured. A server running without a token (loopback development) has no
    credential to present and keeps serving every endpoint unauthenticated,
    exactly like ``/mcp`` does in that mode.
    """

    def __init__(
        self,
        inner: ASGIApp,
        *,
        started_at: float,
        version: str,
        metrics_token: str | None = None,
    ) -> None:
        self._inner = inner
        self._middleware = HealthAndMetricsMiddleware(inner, started_at=started_at, version=version)
        self._metrics_token = metrics_token.strip() if metrics_token else None

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            path = scope.get("path")
            if path == "/metrics":
                if not self._metrics_authorized(scope):
                    response: Response = JSONResponse({"error": "Unauthorized"}, status_code=401)
                    await response(scope, receive, send)
                    return
                await self._middleware(scope, receive, send)
                return
            if path in {"/healthz", "/health"}:
                await self._middleware(scope, receive, send)
                return
        await self._inner(scope, receive, send)

    def _metrics_authorized(self, scope: Any) -> bool:
        if not self._metrics_token:
            return True
        headers = scope_headers(scope)
        provided = bearer_token_from_headers(headers)
        return bearer_token_matches(provided, self._metrics_token)


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


def _terminate_process(signame: str, exit_code: int) -> None:
    """Leave the process now, honouring an interrupt or a termination signal.

    The MCP stdio transport reads stdin through a worker thread whose read
    cannot be interrupted while the client keeps the pipe open: cancelling the
    main task (what ``asyncio`` does on ``SIGINT`` by itself) blocks forever
    on that read, and the container would stay alive until the orchestrator
    escalated to ``SIGKILL``.

    The streams are flushed first, so no partial JSON-RPC frame is left on
    stdout, and the process leaves with the conventional ``128 + signum``
    status that the runtime already reported for ``SIGTERM``.
    """
    logger.info("Received %s, shutting down.", signame)
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):  # pragma: no cover - best effort
            stream.flush()
    os._exit(exit_code)


def _install_stdio_signal_handlers() -> None:
    """Make ``SIGINT``/``SIGTERM`` end the stdio server deterministically.

    Without an explicit handler ``SIGINT`` is swallowed by the event loop and
    the container keeps running with no diagnostic (F-010). ``SIGTERM`` keeps
    the exit status it already had (143); only the shutdown log is new.
    """
    loop = asyncio.get_running_loop()
    for signum, signame, exit_code in (
        (signal.SIGINT, "SIGINT", SIGINT_EXIT_CODE),
        (signal.SIGTERM, "SIGTERM", SIGTERM_EXIT_CODE),
    ):
        try:
            loop.add_signal_handler(signum, _terminate_process, signame, exit_code)
        except (NotImplementedError, RuntimeError):  # pragma: no cover
            logger.warning("Signal %s cannot be handled on this platform.", signame)


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

    # Fail closed on an invalid environment before anything is built or bound.
    settings = Settings.from_env(
        host=host,
        port=port,
        debug=debug,
        stateless=stateless,
        auth_token=auth_token,
        allow_remote_http=allow_remote_http,
        auth_token_env=auth_token_env,
    )
    settings.validate()
    set_settings(settings)
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
        _install_stdio_signal_handlers()
        await server_instance.run_stdio_async()
        logger.info("stdio session ended (EOF on stdin); shutting down.")
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
    port = args.port if args.port is not None else read_port()
    auth_token = os.environ.get(args.auth_token_env, "").strip() or None

    configure_logging()
    # Refuse to start on an invalid environment, before any server object is
    # built, so the operator gets a controlled message naming the variable.
    try:
        Settings.from_env(
            host=args.host,
            port=port,
            debug=args.debug,
            stateless=args.stateless,
            auth_token=auth_token,
            allow_remote_http=args.allow_remote_http,
            auth_token_env=args.auth_token_env,
        ).validate()
    except ConfigurationError as exc:
        logger.error("Invalid configuration: %s", exc)
        raise

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
