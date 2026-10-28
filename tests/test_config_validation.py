"""Regression tests for the bootstrap configuration validation (F-003, F-004).

An out-of-range knob is an operator error: it must be refused at start-up,
with a message that names the offending variable, instead of surfacing as a
runtime failure on the first tool call.
"""

from __future__ import annotations

import pytest

from percival_weather_mcp.config import (
    ConfigurationError,
    Settings,
    read_port,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in (
        "PORT",
        "MCP_WEATHER_PORT",
        "MCP_WEATHER_HTTP_TIMEOUT",
        "MCP_WEATHER_HTTP_MAX_RETRIES",
        "MCP_WEATHER_HTTP_BACKOFF_BASE",
        "MCP_WEATHER_HTTP_BACKOFF_CAP",
        "MCP_WEATHER_HTTP_MAX_CONCURRENCY",
        "MCP_WEATHER_RATE_LIMIT_PER_MINUTE",
    ):
        monkeypatch.delenv(name, raising=False)


def test_defaults_are_valid():
    Settings.from_env().validate()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("PORT", "not-a-number"),
        ("PORT", ""),
        ("MCP_WEATHER_HTTP_TIMEOUT", "abc"),
        ("MCP_WEATHER_HTTP_MAX_RETRIES", "abc"),
        ("MCP_WEATHER_HTTP_MAX_CONCURRENCY", "abc"),
        ("MCP_WEATHER_RATE_LIMIT_PER_MINUTE", "abc"),
    ],
)
def test_malformed_values_are_refused(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ConfigurationError) as excinfo:
        Settings.from_env().validate()
    assert name in str(excinfo.value)


@pytest.mark.parametrize(
    ("name", "value", "expected"),
    [
        ("MCP_WEATHER_HTTP_MAX_RETRIES", "-1", "MCP_WEATHER_HTTP_MAX_RETRIES"),
        ("MCP_WEATHER_HTTP_TIMEOUT", "0", "MCP_WEATHER_HTTP_TIMEOUT"),
        ("MCP_WEATHER_HTTP_TIMEOUT", "-3.5", "MCP_WEATHER_HTTP_TIMEOUT"),
        ("MCP_WEATHER_HTTP_MAX_CONCURRENCY", "0", "MCP_WEATHER_HTTP_MAX_CONCURRENCY"),
        ("MCP_WEATHER_RATE_LIMIT_PER_MINUTE", "0", "MCP_WEATHER_RATE_LIMIT_PER_MINUTE"),
        ("MCP_WEATHER_HTTP_BACKOFF_BASE", "-0.1", "MCP_WEATHER_HTTP_BACKOFF_BASE"),
        ("MCP_WEATHER_HTTP_BACKOFF_CAP", "-1", "MCP_WEATHER_HTTP_BACKOFF_CAP"),
    ],
)
def test_out_of_range_values_are_refused(monkeypatch, name, value, expected):
    monkeypatch.setenv(name, value)
    with pytest.raises(ConfigurationError) as excinfo:
        Settings.from_env().validate()
    assert expected in str(excinfo.value)


def test_negative_retries_never_reach_the_client(monkeypatch):
    """F-004 regression: the retry budget is validated before the first call."""
    monkeypatch.setenv("MCP_WEATHER_HTTP_MAX_RETRIES", "-1")
    with pytest.raises(ConfigurationError):
        Settings.from_env().validate()


@pytest.mark.parametrize("port", [0, -1, 65536, 99999])
def test_port_range_is_enforced(monkeypatch, port):
    monkeypatch.setenv("PORT", str(port))
    with pytest.raises(ConfigurationError) as excinfo:
        Settings.from_env().validate()
    assert "PORT" in str(excinfo.value)


def test_port_prefers_port_over_mcp_weather_port(monkeypatch):
    monkeypatch.setenv("PORT", "9001")
    monkeypatch.setenv("MCP_WEATHER_PORT", "9002")
    assert read_port() == 9001


def test_port_falls_back_to_mcp_weather_port(monkeypatch):
    monkeypatch.setenv("MCP_WEATHER_PORT", "9002")
    assert read_port() == 9002


def test_configuration_error_is_a_value_error():
    """Existing callers keep catching ``ValueError``."""
    assert issubclass(ConfigurationError, ValueError)
