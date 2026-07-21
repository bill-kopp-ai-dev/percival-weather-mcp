"""Regression tests for the server-side metric instrumentation.

These tests guard against the bug where ``_call_handler`` returned a coroutine
without awaiting it, so ``track_tool`` exited before the tool actually
executed. Symptoms included:

* Latency histogram recorded ~0 for every call.
* ``tool_errors`` counter never incremented, even when the tool raised.
* ``tool_calls{status="ok"}`` incremented before the call succeeded.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from percival_weather_mcp import config, observability, server
from percival_weather_mcp.tools.toolhandler import ToolHandler


@pytest.fixture(autouse=True)
def _enable_metrics(monkeypatch):
    """Force the real Prometheus-backed Metrics instance for these tests."""
    observability.reset_metrics()
    monkeypatch.setattr(
        observability,
        "get_settings",
        lambda: config.Settings.from_env(enable_metrics=True),
    )
    observability.reset_metrics()  # required after re-patching get_settings
    yield
    observability.reset_metrics()


class _SlowHandler(ToolHandler):
    input_model = None  # type: ignore[assignment]

    def __init__(self, name: str, *, sleep: float = 0.1, raise_exc: bool = False) -> None:
        super().__init__(name)
        self._sleep = sleep
        self._raise = raise_exc
        self.calls = 0

    def get_tool_description(self):  # type: ignore[override]
        raise NotImplementedError

    async def run_tool(self, args):  # type: ignore[override]
        self.calls += 1
        await asyncio.sleep(self._sleep)
        if self._raise:
            raise RuntimeError("boom")
        return "ok"


@pytest.mark.asyncio
async def test_call_handler_records_real_latency():
    handler = _SlowHandler("slow_tool", sleep=0.1)
    start = time.perf_counter()
    result = await server._call_handler(handler, {})
    elapsed = time.perf_counter() - start
    assert result == "ok"
    # If the bug is back, elapsed will be < 0.01s; with the fix it is >= 0.1s.
    assert elapsed >= 0.1, f"latency was {elapsed:.3f}s, expected >= 0.1s"
    assert handler.calls == 1


@pytest.mark.asyncio
async def test_call_handler_records_errors():
    handler = _SlowHandler("error_tool", sleep=0.0, raise_exc=True)
    with pytest.raises(RuntimeError, match="boom"):
        await server._call_handler(handler, {})

    metrics = observability.get_metrics()
    counter_value = metrics.tool_errors.labels(
        tool="error_tool", exception="RuntimeError"
    )._value.get()
    # Before the fix this counter was always 0.
    assert counter_value >= 1


@pytest.mark.asyncio
async def test_call_handler_records_ok_status():
    handler = _SlowHandler("ok_tool", sleep=0.0)
    await server._call_handler(handler, {})

    metrics = observability.get_metrics()
    counter_value = metrics.tool_calls.labels(tool="ok_tool", status="ok")._value.get()
    assert counter_value >= 1
