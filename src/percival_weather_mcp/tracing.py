"""Optional OpenTelemetry tracing.

Tracing is **off** unless the ``otel`` extra is installed and the
``MCP_WEATHER_ENABLE_TRACING`` environment variable is set to a truthy value.
The functions exposed here are safe to call even when the OpenTelemetry SDK
is unavailable; they simply become no-ops.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Iterator
from typing import Any

from .config import get_settings

logger = logging.getLogger("mcp-weather.tracing")


try:  # pragma: no cover - exercised when the extra is installed
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        ConsoleSpanExporter,
    )

    _OTEL_AVAILABLE = True
except Exception:  # pragma: no cover
    _OTEL_AVAILABLE = False

_initialised = False


def configure_tracing() -> None:
    """Initialise the global tracer provider when tracing is enabled."""
    global _initialised
    settings = get_settings()
    if not settings.enable_tracing:
        return
    if not _OTEL_AVAILABLE:
        logger.warning("MCP_WEATHER_ENABLE_TRACING=true but the 'otel' extra is not installed.")
        return
    if _initialised:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": "percival-weather-mcp"}))
    provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    _initialised = True


@contextlib.contextmanager
def tool_span(name: str, **attributes: Any) -> Iterator[Any]:
    """Open a span around a tool call when tracing is active."""
    if not get_settings().enable_tracing or not _OTEL_AVAILABLE:
        yield None
        return
    tracer = trace.get_tracer("percival-weather-mcp")
    with tracer.start_as_current_span(name, attributes=attributes) as span:
        yield span
