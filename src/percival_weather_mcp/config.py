"""Runtime configuration constants for the Percival Weather MCP server."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080
DEFAULT_AUTH_TOKEN_ENV_VAR = "MCP_WEATHER_AUTH_TOKEN"
SERVER_NAME = "percival-weather-mcp"

# HTTP transport
DEFAULT_HTTP_TIMEOUT_SECONDS = 15.0
DEFAULT_HTTP_MAX_RETRIES = 2
DEFAULT_HTTP_BACKOFF_BASE = 0.3
DEFAULT_HTTP_BACKOFF_CAP = 2.0
DEFAULT_HTTP_MAX_CONCURRENCY = 16

# Geocoding cache
GEO_CACHE_TTL_SECONDS = 1800.0
GEO_CACHE_MAX_SIZE = 512
MAX_DATE_RANGE_DAYS = 16

# Circuit breaker for geocoding
GEO_BREAKER_FAIL_THRESHOLD = 5
GEO_BREAKER_RESET_SECONDS = 60.0

# Rate limiting
RATE_LIMIT_DEFAULT_PER_MINUTE = 120

# Observability
SERVER_STARTED_AT_KEY = "server_started_at"

#: Upper bound for ``MCP_WEATHER_HTTP_MAX_RETRIES``. Beyond this the server
#: would hammer a public, rate-limited upstream for a single tool call.
MAX_HTTP_MAX_RETRIES = 10


class ConfigurationError(ValueError):
    """Raised when the runtime configuration is invalid.

    The server refuses to start on this error: an out-of-range knob is an
    operator mistake, and discovering it at the first request (or never) is
    worse than failing at boot with a message that names the offending
    variable.
    """


@dataclass(frozen=True)
class Settings:
    """Process-wide runtime settings, populated from env / CLI."""

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    debug: bool = False
    stateless: bool = False
    auth_token: str | None = None
    allow_remote_http: bool = False
    auth_token_env: str = DEFAULT_AUTH_TOKEN_ENV_VAR
    http_timeout: float = DEFAULT_HTTP_TIMEOUT_SECONDS
    http_max_retries: int = DEFAULT_HTTP_MAX_RETRIES
    http_backoff_base: float = DEFAULT_HTTP_BACKOFF_BASE
    http_backoff_cap: float = DEFAULT_HTTP_BACKOFF_CAP
    http_max_concurrency: int = DEFAULT_HTTP_MAX_CONCURRENCY
    rate_limit_per_minute: int = RATE_LIMIT_DEFAULT_PER_MINUTE
    log_format: str = "text"  # or "json"
    enable_metrics: bool = True
    enable_tracing: bool = False
    geo_breaker_fail_threshold: int = GEO_BREAKER_FAIL_THRESHOLD
    geo_breaker_reset_seconds: float = GEO_BREAKER_RESET_SECONDS
    geo_cache_ttl_seconds: float = GEO_CACHE_TTL_SECONDS
    geo_cache_max_size: int = GEO_CACHE_MAX_SIZE
    max_date_range_days: int = MAX_DATE_RANGE_DAYS

    @classmethod
    def from_env(cls, **overrides: object) -> Settings:
        values: dict[str, object] = {
            "host": os.environ.get("MCP_WEATHER_HOST", DEFAULT_HOST),
            "port": read_port(),
            "auth_token_env": os.environ.get(
                "MCP_WEATHER_AUTH_TOKEN_ENV", DEFAULT_AUTH_TOKEN_ENV_VAR
            ),
            "http_timeout": _env_float("MCP_WEATHER_HTTP_TIMEOUT", DEFAULT_HTTP_TIMEOUT_SECONDS),
            "http_max_retries": _env_int("MCP_WEATHER_HTTP_MAX_RETRIES", DEFAULT_HTTP_MAX_RETRIES),
            "http_backoff_base": _env_float(
                "MCP_WEATHER_HTTP_BACKOFF_BASE", DEFAULT_HTTP_BACKOFF_BASE
            ),
            "http_backoff_cap": _env_float(
                "MCP_WEATHER_HTTP_BACKOFF_CAP", DEFAULT_HTTP_BACKOFF_CAP
            ),
            "http_max_concurrency": _env_int(
                "MCP_WEATHER_HTTP_MAX_CONCURRENCY", DEFAULT_HTTP_MAX_CONCURRENCY
            ),
            "rate_limit_per_minute": _env_int(
                "MCP_WEATHER_RATE_LIMIT_PER_MINUTE", RATE_LIMIT_DEFAULT_PER_MINUTE
            ),
            "log_format": os.environ.get("MCP_WEATHER_LOG_FORMAT", "text").lower(),
            "enable_metrics": _env_bool("MCP_WEATHER_ENABLE_METRICS", True),
            "enable_tracing": _env_bool("MCP_WEATHER_ENABLE_TRACING", False),
        }
        values.update(overrides)
        return cls(**values)  # type: ignore[arg-type]

    def validate(self) -> None:
        """Raise :class:`ConfigurationError` when a setting is out of range.

        Called by the CLI bootstrap before the server object is built, so an
        invalid environment fails closed with a message naming the variable
        instead of surfacing as a runtime error on the first tool call.
        """
        if not 1 <= self.port <= 65535:
            raise ConfigurationError(f"PORT must be between 1 and 65535 (got {self.port}).")
        if self.http_timeout <= 0:
            raise ConfigurationError(
                f"MCP_WEATHER_HTTP_TIMEOUT must be greater than 0 (got {self.http_timeout})."
            )
        if self.http_max_retries < 0:
            raise ConfigurationError(
                f"MCP_WEATHER_HTTP_MAX_RETRIES must be 0 or greater (got {self.http_max_retries})."
            )
        if self.http_max_retries > MAX_HTTP_MAX_RETRIES:
            raise ConfigurationError(
                f"MCP_WEATHER_HTTP_MAX_RETRIES must be at most {MAX_HTTP_MAX_RETRIES} "
                f"(got {self.http_max_retries})."
            )
        if self.http_backoff_base < 0:
            raise ConfigurationError(
                "MCP_WEATHER_HTTP_BACKOFF_BASE must not be negative "
                f"(got {self.http_backoff_base})."
            )
        if self.http_backoff_cap < 0:
            raise ConfigurationError(
                "MCP_WEATHER_HTTP_BACKOFF_CAP must not be negative (got {self.http_backoff_cap})."
            )
        if self.http_max_concurrency < 1:
            raise ConfigurationError(
                "MCP_WEATHER_HTTP_MAX_CONCURRENCY must be at least 1 "
                f"(got {self.http_max_concurrency})."
            )
        if self.rate_limit_per_minute < 1:
            raise ConfigurationError(
                "MCP_WEATHER_RATE_LIMIT_PER_MINUTE must be at least 1 "
                f"(got {self.rate_limit_per_minute})."
            )


def _env_int(name: str, default: int) -> int:
    """Read an integer env var, refusing malformed values with a clear message."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except ValueError:
        raise ConfigurationError(f"{name} must be an integer (got {raw!r}).") from None


def _env_float(name: str, default: float) -> float:
    """Read a float env var, refusing malformed values with a clear message."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw.strip())
    except ValueError:
        raise ConfigurationError(f"{name} must be a number (got {raw!r}).") from None


def read_port() -> int:
    """Read the listening port, preferring ``PORT`` over ``MCP_WEATHER_PORT``."""
    if "PORT" in os.environ:
        return _env_int("PORT", DEFAULT_PORT)
    return _env_int("MCP_WEATHER_PORT", DEFAULT_PORT)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# Module-level mutable settings (kept for backward compatibility with code that
# imported the older module-level constants). ``server.py`` is the single
# writer; everything else should depend on ``get_settings()``.
#
# The import-time construction never raises: a malformed environment is an
# operator error that must be reported by the CLI bootstrap as a controlled
# message, not as an import-time traceback. ``Settings.from_env()`` re-raises
# it with the same detail as soon as the bootstrap asks for the real values.
try:
    _runtime_settings: Settings = Settings.from_env()
except ConfigurationError:
    _runtime_settings = Settings()


def get_settings() -> Settings:
    """Return the current process-wide settings."""
    return _runtime_settings


def set_settings(settings: Settings) -> None:
    """Update the process-wide settings (intended for tests and CLI bootstrap)."""
    global _runtime_settings
    _runtime_settings = settings


# Backward-compatible aliases (these were previously module-level constants).
DEFAULT_HOST_VALUE = DEFAULT_HOST
DEFAULT_PORT_VALUE = DEFAULT_PORT
DEFAULT_AUTH_TOKEN_ENV_VAR_VALUE = DEFAULT_AUTH_TOKEN_ENV_VAR
