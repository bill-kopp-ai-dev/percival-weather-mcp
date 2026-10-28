"""Tests for the HTTP endpoint authentication policy (F-016, A-011).

``/healthz`` and ``/health`` stay open — they are liveness probes for
orchestrators that do not hold the bearer token. ``/metrics`` carries
operational counters and therefore requires the token whenever one is
configured.
"""

from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from percival_weather_mcp.server import _ASGIWrapper

TOKEN = "a" * 32


async def _ok(request):  # pragma: no cover - never reached in these tests
    return PlainTextResponse("inner")


def _wrapper(token: str | None) -> _ASGIWrapper:
    app = Starlette(routes=[Route("/inner", _ok)])
    return _ASGIWrapper(app, started_at=0.0, version="0.9.0", metrics_token=token)


async def _call(wrapper: _ASGIWrapper, path: str, headers: dict[str, str] | None = None):
    """Drive the ASGI wrapper and return (status_code, body)."""
    raw_headers = [
        (name.encode("latin-1"), value.encode("latin-1")) for name, value in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": raw_headers,
        "query_string": b"",
    }
    messages: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(message):
        messages.append(message)

    await wrapper(scope, receive, send)

    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return status, body.decode()


@pytest.mark.asyncio
async def test_healthz_stays_open_without_a_token():
    status, body = await _call(_wrapper(TOKEN), "/healthz")
    assert status == 200
    assert "percival-weather-mcp" in body


@pytest.mark.asyncio
async def test_health_alias_stays_open_without_a_token():
    status, _body = await _call(_wrapper(TOKEN), "/health")
    assert status == 200


@pytest.mark.asyncio
async def test_metrics_requires_the_bearer_token():
    status, body = await _call(_wrapper(TOKEN), "/metrics")
    assert status == 401
    assert "Unauthorized" in body


@pytest.mark.asyncio
async def test_metrics_rejects_a_wrong_token():
    status, _body = await _call(_wrapper(TOKEN), "/metrics", {"authorization": "Bearer nope"})
    assert status == 401


@pytest.mark.asyncio
async def test_metrics_accepts_the_configured_token():
    status, _body = await _call(_wrapper(TOKEN), "/metrics", {"authorization": f"Bearer {TOKEN}"})
    assert status == 200


@pytest.mark.asyncio
async def test_metrics_accepts_the_x_mcp_auth_token_header():
    status, _body = await _call(_wrapper(TOKEN), "/metrics", {"x-mcp-auth-token": TOKEN})
    assert status == 200


@pytest.mark.asyncio
async def test_metrics_stays_open_when_no_token_is_configured():
    """Without a token there is no credential to present, as with ``/mcp``."""
    status, _body = await _call(_wrapper(None), "/metrics")
    assert status == 200
