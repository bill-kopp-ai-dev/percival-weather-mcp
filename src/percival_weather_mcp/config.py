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
            "port": int(os.environ.get("PORT", os.environ.get("MCP_WEATHER_PORT", DEFAULT_PORT))),
            "auth_token_env": os.environ.get(
                "MCP_WEATHER_AUTH_TOKEN_ENV", DEFAULT_AUTH_TOKEN_ENV_VAR
            ),
            "http_timeout": float(
                os.environ.get("MCP_WEATHER_HTTP_TIMEOUT", DEFAULT_HTTP_TIMEOUT_SECONDS)
            ),
            "http_max_retries": int(
                os.environ.get("MCP_WEATHER_HTTP_MAX_RETRIES", DEFAULT_HTTP_MAX_RETRIES)
            ),
            "http_backoff_base": float(
                os.environ.get("MCP_WEATHER_HTTP_BACKOFF_BASE", DEFAULT_HTTP_BACKOFF_BASE)
            ),
            "http_backoff_cap": float(
                os.environ.get("MCP_WEATHER_HTTP_BACKOFF_CAP", DEFAULT_HTTP_BACKOFF_CAP)
            ),
            "http_max_concurrency": int(
                os.environ.get("MCP_WEATHER_HTTP_MAX_CONCURRENCY", DEFAULT_HTTP_MAX_CONCURRENCY)
            ),
            "rate_limit_per_minute": int(
                os.environ.get("MCP_WEATHER_RATE_LIMIT_PER_MINUTE", RATE_LIMIT_DEFAULT_PER_MINUTE)
            ),
            "log_format": os.environ.get("MCP_WEATHER_LOG_FORMAT", "text").lower(),
            "enable_metrics": _env_bool("MCP_WEATHER_ENABLE_METRICS", True),
            "enable_tracing": _env_bool("MCP_WEATHER_ENABLE_TRACING", False),
        }
        values.update(overrides)
        return cls(**values)  # type: ignore[arg-type]


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# Module-level mutable settings (kept for backward compatibility with code that
# imported the older module-level constants). ``server.py`` is the single
# writer; everything else should depend on ``get_settings()``.
_runtime_settings: Settings = Settings.from_env()


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
