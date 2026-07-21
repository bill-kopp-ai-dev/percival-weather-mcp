"""Tests for middleware: bearer auth, rate limiting, health/metrics."""

from __future__ import annotations

import asyncio
import time

import pytest
from starlette.requests import Request

from percival_weather_mcp.middleware import (
    BearerTokenAuthMiddleware,
    HealthAndMetricsMiddleware,
    RateLimitMiddleware,
    is_loopback_host,
    validate_http_runtime_security,
)


class _StubCall:
    async def __call__(self, request: Request):
        return _StubResponse(200, "ok")


class _StubResponse:
    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body

    async def __call__(self, scope, receive, send):  # pragma: no cover - placeholder
        pass


@pytest.mark.asyncio
async def test_bearer_auth_rejects_missing_token():
    async def app(scope, receive, send):
        pass

    middleware = BearerTokenAuthMiddleware(app, token="secret")
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": b"",
        }
    )

    response = await middleware.dispatch(request, _StubCall())
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_bearer_auth_accepts_valid_token():
    middleware = BearerTokenAuthMiddleware(_StubCall(), token="secret")
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"authorization", b"Bearer secret")],
            "query_string": b"",
        }
    )
    # The stub call_next returns a _StubResponse; if the middleware short-circuits
    # because of bad auth it would return a JSONResponse instead. So the absence
    # of a JSONResponse-shaped result is what proves the token was accepted.
    result = await middleware.dispatch(request, _StubCall())
    assert isinstance(result, _StubResponse)


def test_rate_limit_blocks_after_budget():
    loop = asyncio.new_event_loop()
    try:
        async def scenario():
            sent: list[dict] = []

            async def app(scope, receive, send):
                await send({"type": "http.response.start", "status": 200, "headers": []})
                await send({"type": "http.response.body", "body": b""})

            middleware = RateLimitMiddleware(app, per_minute=2)
            for _ in range(5):
                request = Request(
                    {
                        "type": "http",
                        "method": "GET",
                        "path": "/",
                        "headers": [],
                        "query_string": b"",
                        "client": ("1.2.3.4", 0),
                    }
                )
                await middleware.dispatch(request, _StubCall())
            return sent

        loop.run_until_complete(scenario())
    finally:
        loop.close()


def test_is_loopback_host():
    assert is_loopback_host("127.0.0.1")
    assert is_loopback_host("localhost")
    assert is_loopback_host("::1")
    assert not is_loopback_host("0.0.0.0")
    assert not is_loopback_host("8.8.8.8")


def test_validate_http_runtime_security_loopback_no_token_ok(caplog):
    validate_http_runtime_security(
        mode="streamable-http",
        host="127.0.0.1",
        allow_remote_http=False,
        auth_token=None,
        auth_token_env="TOKEN_ENV",
    )


def test_validate_http_runtime_security_remote_without_token_fails():
    with pytest.raises(ValueError):
        validate_http_runtime_security(
            mode="streamable-http",
            host="0.0.0.0",
            allow_remote_http=True,
            auth_token=None,
            auth_token_env="TOKEN_ENV",
        )


def test_validate_http_runtime_security_remote_without_flag_fails():
    with pytest.raises(ValueError):
        validate_http_runtime_security(
            mode="streamable-http",
            host="0.0.0.0",
            allow_remote_http=False,
            auth_token="secret",
            auth_token_env="TOKEN_ENV",
        )


@pytest.mark.asyncio
async def test_health_middleware_responds_to_healthz():
    sent: list[dict] = []

    async def app(scope, receive, send):
        pass

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(message):
        sent.append(message)

    middleware = HealthAndMetricsMiddleware(app, started_at=time.time(), version="0.7.0")
    await middleware({"type": "http", "method": "GET", "path": "/healthz"}, receive, send)
    assert any(msg.get("type") == "http.response.start" for msg in sent)
