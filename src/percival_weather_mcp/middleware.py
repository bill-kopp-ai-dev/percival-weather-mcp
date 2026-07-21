"""HTTP middleware: bearer-token auth, rate limiting, metrics endpoint."""

from __future__ import annotations

import hmac
import logging
import threading
import time
from collections.abc import Awaitable, Callable
from ipaddress import ip_address
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from .config import get_settings
from .observability import get_metrics

logger = logging.getLogger("mcp-weather.middleware")


class BearerTokenAuthMiddleware(BaseHTTPMiddleware):
    """Reject requests without a matching bearer token."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        super().__init__(app)
        self._token = token.strip()

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
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


class _TokenBucket:
    """Thread-safe token bucket used by :class:`RateLimitMiddleware`."""

    def __init__(self, capacity: int, refill_per_second: float) -> None:
        self._capacity = capacity
        self._refill_per_second = refill_per_second
        self._lock = threading.Lock()
        self._tokens = float(capacity)
        self._last = time.monotonic()

    def try_consume(self, tokens: float = 1.0) -> bool:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._last = now
            self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_per_second)
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory per-IP token-bucket rate limiter."""

    def __init__(self, app: ASGIApp, per_minute: int) -> None:
        super().__init__(app)
        self._per_minute = max(1, per_minute)
        self._refill_per_second = self._per_minute / 60.0
        self._buckets: dict[str, _TokenBucket] = {}
        self._lock = threading.Lock()

    def _bucket_for(self, client_host: str) -> _TokenBucket:
        with self._lock:
            bucket = self._buckets.get(client_host)
            if bucket is None:
                bucket = _TokenBucket(self._per_minute, self._refill_per_second)
                self._buckets[client_host] = bucket
            return bucket

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        client_host = (request.client.host if request.client else "unknown") or "unknown"
        if not self._bucket_for(client_host).try_consume():
            return JSONResponse(
                {"error": "Too Many Requests"},
                status_code=429,
                headers={"Retry-After": "1"},
            )
        return await call_next(request)


class HealthAndMetricsMiddleware:
    """Expose ``GET /healthz`` and ``GET /metrics`` without bypassing auth.

    This is implemented as a pure ASGI middleware so it can be installed in
    front of the FastMCP Starlette app and respond before any authentication
    checks for health probes.
    """

    def __init__(self, app: ASGIApp, *, started_at: float, version: str) -> None:
        self.app = app
        self._started_at = started_at
        self._version = version

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in {"/healthz", "/health"}:
            health_response: Response = JSONResponse(
                {
                    "status": "ok",
                    "server": "percival-weather-mcp",
                    "version": self._version,
                    "uptime_seconds": round(time.time() - self._started_at, 3),
                }
            )
            await health_response(scope, receive, send)
            return
        if path == "/metrics":
            payload, content_type = get_metrics().render()
            metrics_response: Response = Response(content=payload, media_type=content_type)
            await metrics_response(scope, receive, send)
            return

        await self.app(scope, receive, send)


def is_loopback_host(host: str) -> bool:
    """Return True if the host resolves to a loopback address."""
    normalised = host.strip().lower()
    if normalised in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        return ip_address(normalised).is_loopback
    except ValueError:
        return False


def validate_http_runtime_security(
    *,
    mode: str,
    host: str,
    allow_remote_http: bool,
    auth_token: str | None,
    auth_token_env: str,
) -> None:
    """Refuse unsafe HTTP configurations early."""
    if mode not in {"sse", "streamable-http"}:
        return

    loopback = is_loopback_host(host)
    if not loopback and not allow_remote_http:
        raise ValueError(
            "Refusing to bind HTTP transport to a non-loopback host without --allow-remote-http."
        )
    if not loopback and not auth_token:
        raise ValueError(
            "Remote HTTP mode requires authentication. "
            f"Set {auth_token_env} or choose a different token env var with --auth-token-env."
        )
    if loopback and not auth_token:
        logger.warning(
            "Starting HTTP mode on loopback host without authentication token. "
            "This is acceptable for local development only."
        )


def install_security_middleware(app: Any, *, auth_token: str | None) -> None:
    """Install rate-limit + auth middlewares on a Starlette/FastMCP app."""
    settings = get_settings()
    app.add_middleware(RateLimitMiddleware, per_minute=settings.rate_limit_per_minute)
    if auth_token:
        app.add_middleware(BearerTokenAuthMiddleware, token=auth_token)
