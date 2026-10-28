"""Tests for the stdio lifecycle and its signal handling (F-010, F-011).

``SIGINT`` used to be swallowed by the event loop: the container stayed alive
until the orchestrator escalated to ``SIGKILL``. The server now installs its
own handlers and leaves with the conventional ``128 + signum`` status.
"""

from __future__ import annotations

import asyncio
import signal

import pytest

from percival_weather_mcp import server as weather_server


@pytest.fixture
def _restore_signal_handlers():
    """Restore the previous SIGINT/SIGTERM handlers after the test."""
    previous = {signum: signal.getsignal(signum) for signum in (signal.SIGINT, signal.SIGTERM)}
    yield
    for signum, handler in previous.items():
        signal.signal(signum, handler)


def test_stdio_handlers_replace_the_default_sigint_handler(_restore_signal_handlers):
    """Without an explicit handler, SIGINT never reaches the server."""
    assert signal.getsignal(signal.SIGINT) is signal.default_int_handler

    async def scenario() -> tuple[object, object]:
        weather_server._install_stdio_signal_handlers()
        # The check must happen while the loop is running: asyncio restores
        # the previous handlers when the loop closes.
        return signal.getsignal(signal.SIGINT), signal.getsignal(signal.SIGTERM)

    sigint_handler, sigterm_handler = asyncio.run(scenario())

    assert sigint_handler is not signal.default_int_handler
    assert sigterm_handler is not signal.SIG_DFL


def test_terminate_process_uses_the_conventional_status(monkeypatch):
    """The exit status must stay 128 + signum so the runtime contract holds."""
    calls: list[int] = []

    def fake_exit(code: int) -> None:
        calls.append(code)

    monkeypatch.setattr(weather_server.os, "_exit", fake_exit)

    weather_server._terminate_process("SIGINT", weather_server.SIGINT_EXIT_CODE)

    assert calls == [130]
    assert 128 + int(signal.SIGINT) == weather_server.SIGINT_EXIT_CODE
    assert 128 + int(signal.SIGTERM) == weather_server.SIGTERM_EXIT_CODE


def test_terminate_process_flushes_stdout_before_leaving(monkeypatch):
    """A partial JSON-RPC frame must never be left on stdout."""
    flushed: list[str] = []

    class _Stream:
        def __init__(self, name: str) -> None:
            self._name = name

        def flush(self) -> None:
            flushed.append(self._name)

    monkeypatch.setattr(weather_server.os, "_exit", lambda code: None)
    monkeypatch.setattr(weather_server.sys, "stdout", _Stream("stdout"))
    monkeypatch.setattr(weather_server.sys, "stderr", _Stream("stderr"))

    weather_server._terminate_process("SIGTERM", weather_server.SIGTERM_EXIT_CODE)

    assert flushed == ["stdout", "stderr"]
