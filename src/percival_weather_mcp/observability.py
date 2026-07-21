"""Lightweight observability primitives: counters, histograms and exporters.

We deliberately avoid a hard dependency on ``prometheus_client`` at import
time. When ``MCP_WEATHER_ENABLE_METRICS`` is enabled and the library is
installed, the helpers below transparently route to it; otherwise they fall
back to no-op implementations.
"""

from __future__ import annotations

import contextlib
import logging
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from typing import Any

from .config import get_settings

logger = logging.getLogger("mcp-weather.metrics")


try:  # pragma: no cover - exercised indirectly when dep is available
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        Counter,
        Histogram,
        generate_latest,
    )

    _PROM_AVAILABLE = True
except Exception:  # pragma: no cover
    _PROM_AVAILABLE = False


class _NoopMetric:
    def labels(self, **_: Any) -> _NoopMetric:
        return self

    def inc(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def observe(self, *_args: Any, **_kwargs: Any) -> None:
        return None


_NOOP = _NoopMetric()


class Metrics:
    """Container for the metrics used across the server."""

    def __init__(self) -> None:
        self.enabled = get_settings().enable_metrics and _PROM_AVAILABLE
        # ``Any`` keeps the no-op fallback compatible with the real Prometheus
        # metric objects without resorting to ``type: ignore`` everywhere.
        self.tool_calls: Any = _NOOP
        self.tool_errors: Any = _NOOP
        self.tool_latency: Any = _NOOP
        self.http_requests: Any = _NOOP
        self.http_errors: Any = _NOOP
        self.registry: CollectorRegistry | None = None
        if not self.enabled:
            return

        self.registry = CollectorRegistry()
        self.tool_calls = Counter(
            "mcp_weather_tool_calls_total",
            "Total number of MCP tool invocations.",
            ["tool", "status"],
            registry=self.registry,
        )
        self.tool_errors = Counter(
            "mcp_weather_tool_errors_total",
            "Total number of MCP tool errors, by exception class.",
            ["tool", "exception"],
            registry=self.registry,
        )
        self.tool_latency = Histogram(
            "mcp_weather_tool_latency_seconds",
            "Latency of MCP tool invocations.",
            ["tool"],
            registry=self.registry,
        )
        self.http_requests = Counter(
            "mcp_weather_http_requests_total",
            "Total number of outbound HTTP requests.",
            ["upstream", "status"],
            registry=self.registry,
        )
        self.http_errors = Counter(
            "mcp_weather_http_errors_total",
            "Total number of outbound HTTP errors.",
            ["upstream", "exception"],
            registry=self.registry,
        )

    def render(self) -> tuple[bytes, str]:
        if not self.enabled or self.registry is None:
            return b"", "text/plain; version=0.0.4"
        return generate_latest(self.registry), CONTENT_TYPE_LATEST


_metrics: Metrics | None = None


def get_metrics() -> Metrics:
    """Return the lazily-initialised metrics container."""
    global _metrics
    if _metrics is None:
        _metrics = Metrics()
    return _metrics


def reset_metrics() -> None:
    """Reset the metrics container (intended for tests)."""
    global _metrics
    _metrics = None


@contextmanager
def track_tool(tool_name: str) -> Iterator[dict[str, Any]]:
    """Synchronous context manager that records tool-call latency.

    For coroutine tool handlers use :func:`track_tool_async` instead, which
    measures the time spent inside the coroutine (not just the time spent
    creating it).
    """
    metrics = get_metrics()
    state: dict[str, Any] = {"exception": None}
    start = time.perf_counter()
    try:
        yield state
        metrics.tool_calls.labels(tool=tool_name, status="ok").inc()
    except Exception as exc:
        metrics.tool_calls.labels(tool=tool_name, status="error").inc()
        metrics.tool_errors.labels(
            tool=tool_name, exception=type(exc).__name__
        ).inc()
        state["exception"] = exc
        raise
    finally:
        metrics.tool_latency.labels(tool=tool_name).observe(
            time.perf_counter() - start
        )


@contextlib.asynccontextmanager
async def track_tool_async(tool_name: str) -> AsyncIterator[dict[str, Any]]:
    """Async context manager that records tool-call latency around an awaited coroutine.

    Usage::

        async with track_tool_async("my_tool") as state:
            state["result"] = await handler.run_tool(args)
    """
    metrics = get_metrics()
    state: dict[str, Any] = {"exception": None, "result": None}
    start = time.perf_counter()
    try:
        yield state
        metrics.tool_calls.labels(tool=tool_name, status="ok").inc()
    except BaseException as exc:
        metrics.tool_calls.labels(tool=tool_name, status="error").inc()
        metrics.tool_errors.labels(
            tool=tool_name, exception=type(exc).__name__
        ).inc()
        state["exception"] = exc
        raise
    finally:
        metrics.tool_latency.labels(tool=tool_name).observe(
            time.perf_counter() - start
        )


def record_http_request(upstream: str, status: str) -> None:
    get_metrics().http_requests.labels(upstream=upstream, status=status).inc()


def record_http_error(upstream: str, exc: BaseException) -> None:
    get_metrics().http_errors.labels(
        upstream=upstream, exception=type(exc).__name__
    ).inc()
