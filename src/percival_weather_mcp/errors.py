"""Error taxonomy for the Percival Weather MCP server.

In the stdio transport the tool result is the agent's *only* signal: there is
no log channel it can read. A failure that is reported with the wrong cause
therefore makes the agent take the wrong action — historically an upstream
rate limit (HTTP 429) was reported as "invalid request", which invites the
agent to rewrite the city name instead of retrying later.

Three classes are distinguished, and each one carries its own agent-facing
message:

* :class:`InvalidRequestError` — the request was rejected by **local**
  validation (bad date range, unknown timezone, malformed city name). The
  upstream was never contacted, so changing the input is the right move.
* :class:`NoDataError` — the upstream answered successfully but there is
  nothing to report (empty hourly series, city absent from the geocoding
  catalogue). This is neither an upstream failure nor a local validation
  failure, and must not be reported as either.
* :class:`UpstreamError` — the upstream itself failed: an HTTP status, a
  timeout, a network error or an open circuit breaker.

All of them derive from :class:`WeatherMCPError`, which derives from
``RuntimeError``. The tool handlers already re-raise ``RuntimeError``
untouched, so the FastMCP layer keeps turning them into an ``isError`` tool
result whose text is the exception message.
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "InvalidRequestError",
    "NoDataError",
    "UpstreamError",
    "WeatherMCPError",
    "no_data_found",
    "service_label",
    "status_reason",
    "upstream_http_error",
    "upstream_invalid_response",
    "upstream_timeout",
    "upstream_unreachable",
]


class WeatherMCPError(RuntimeError):
    """Base class for every failure the server reports back to the agent."""


class InvalidRequestError(WeatherMCPError):
    """The request was rejected by local validation; the upstream was never called."""


class NoDataError(WeatherMCPError):
    """The upstream answered successfully but returned no usable data."""


class UpstreamError(WeatherMCPError):
    """The upstream provider failed, refused the request or timed out.

    Attributes:
        service: Logical name of the upstream call (``weather``, ``geocoding``…).
        status_code: HTTP status returned by the provider, when there was one.
        reason: Machine-readable cause (``http_error``, ``timeout``,
            ``network_error``, ``invalid_response``, ``circuit_open``,
            ``internal_error``).
    """

    def __init__(
        self,
        message: str,
        *,
        service: str,
        status_code: int | None = None,
        reason: str = "unknown",
    ) -> None:
        super().__init__(message)
        self.service = service
        self.status_code = status_code
        self.reason = reason


# ---------------------------------------------------------------------------
# Message construction.
#
# Every upstream failure reaches the agent through one of these helpers, so the
# wording stays consistent and always names the external cause explicitly.
# ---------------------------------------------------------------------------

_SERVICE_LABELS: Final[dict[str, str]] = {
    "weather": "weather forecast",
    "geocoding": "geocoding",
    "air-quality": "air quality",
    "air-quality-tools": "air quality",
    "shared": "upstream",
}

_STATUS_REASONS: Final[dict[int, str]] = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    408: "Request Timeout",
    409: "Conflict",
    410: "Gone",
    413: "Payload Too Large",
    422: "Unprocessable Entity",
    429: "Too Many Requests",
    500: "Internal Server Error",
    502: "Bad Gateway",
    503: "Service Unavailable",
    504: "Gateway Timeout",
}


def service_label(service: str) -> str:
    """Return the human-readable name used in agent-facing messages."""
    return _SERVICE_LABELS.get(service, service)


def status_reason(status_code: int) -> str:
    """Return the reason phrase for ``status_code`` (falls back to a generic one)."""
    return _STATUS_REASONS.get(status_code, "HTTP error")


def _http_guidance(service: str, status_code: int) -> str:
    """Return the actionable orientation that matches the failure class."""
    if status_code == 429:
        return "The provider is rate limiting this client; retry in a few minutes."
    if status_code >= 500:
        return "The provider failed to answer; retry shortly."
    if status_code == 404 and service == "geocoding":
        return "The location was not found upstream; check the city name."
    return (
        "The request was rejected upstream; check the location name and the requested parameters."
    )


def upstream_http_error(service: str, status_code: int) -> UpstreamError:
    """Build the error for a non-200 HTTP response from the upstream."""
    label = service_label(service)
    reason = status_reason(status_code)
    message = (
        f"Upstream Open-Meteo {label} returned HTTP {status_code} ({reason}). "
        f"{_http_guidance(service, status_code)}"
    )
    return UpstreamError(
        message,
        service=service,
        status_code=status_code,
        reason="http_error",
    )


def upstream_timeout(service: str, timeout_seconds: float) -> UpstreamError:
    """Build the error for an upstream request that exceeded the timeout."""
    label = service_label(service)
    message = (
        f"Upstream Open-Meteo {label} timed out after {timeout_seconds:g}s. "
        "The provider did not answer in time; retry shortly."
    )
    return UpstreamError(message, service=service, reason="timeout")


def upstream_unreachable(service: str, detail: str) -> UpstreamError:
    """Build the error for an upstream that could not be reached at all."""
    label = service_label(service)
    message = (
        f"Upstream Open-Meteo {label} could not be reached ({detail}). "
        "Check the network path and retry shortly."
    )
    return UpstreamError(message, service=service, reason="network_error")


def upstream_invalid_response(service: str) -> UpstreamError:
    """Build the error for a 2xx response whose body is not the expected JSON."""
    label = service_label(service)
    message = (
        f"Upstream Open-Meteo {label} returned a response that could not be parsed as JSON. "
        "The provider may be misbehaving; retry shortly."
    )
    return UpstreamError(message, service=service, reason="invalid_response")


def no_data_found(service: str, subject: str, hint: str) -> NoDataError:
    """Build the error for a successful upstream answer without usable data."""
    label = service_label(service)
    return NoDataError(f"Open-Meteo {label} returned no data for {subject}. {hint}")
