# Changelog

All notable changes to **percival-weather-mcp** are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
the project adheres to [Semantic Versioning](https://semver.org/).

## [0.7.0] - 2026-07-21

### Added
- Shared `ResilientHttpClient` with retries, jittered exponential backoff,
  per-process concurrency cap and circuit-breaker for the geocoding upstream.
- New `percival_weather_mcp.config.Settings` consolidating every runtime
  configuration value (host, port, timeouts, retries, breaker thresholds,
  rate-limit, log format, observability toggles) populated from environment
  variables.
- `HealthAndMetricsMiddleware` exposing `GET /healthz`, `GET /health` and
  `GET /metrics` (Prometheus) on HTTP transports.
- `RateLimitMiddleware` providing a per-IP token-bucket limiter for HTTP
  transports (default 120 req/min, configurable via env var).
- TLS support for HTTP transports (`--ssl-keyfile`, `--ssl-certfile`).
- Pydantic input models for every tool, replacing the dynamic signature
  builder and removing the fragile JSON-Schema → annotation translation.
- Dedicated presentation layer (`percival_weather_mcp.presentation`) for
  weather and air-quality formatters.
- Structured (JSON) logging via `MCP_WEATHER_LOG_FORMAT=json`.
- Optional OpenTelemetry tracing via `MCP_WEATHER_ENABLE_TRACING=true` and
  the new `otel` extra.
- Sanitisation of timezone names (control chars, length cap, forbidden
  character set) before they reach `ZoneInfo`.
- Initial unit test suite (`pytest` + `pytest-asyncio` + `respx`) covering
  `utils`, formatters and the resilient HTTP client.

### Changed
- The `mcp_weather_server` compatibility package now contains only three
  shim files (`__init__.py`, `__main__.py`, `server.py`); the duplicated
  `tools/` tree was removed and the package re-exports from
  `percival_weather_mcp`.
- Consolidated all tool registration through `register_all_tools()`; the
  standalone `@app.tool("weather_get_status")` decorator was removed and
  re-implemented as a regular handler.
- `datetime.utcnow()` was replaced with `datetime.now(timezone.utc)` and
  naive `datetime.now()` calls in tool handlers now use UTC explicitly.
- `weather_get_details` now fetches the current conditions plus forecast in
  a single HTTP request when `include_forecast=true` (was two calls).
- `tool_handlers.run_tool` validates inputs through the Pydantic model,
  surfacing clearer error messages.
- The default `MODE` constants were moved into `percival_weather_mcp.config`
  and the previous module-level constants now resolve to those values for
  backward compatibility.

### Security
- Rate limiting prevents accidental floods of the Open-Meteo APIs.
- TLS support enables direct HTTPS deployments without a reverse proxy.
- Stricter timezone validation reduces attack surface on the `ZoneInfo`
  lookup path.

## [0.6.1] - 2025-04-09

Initial public release as a standalone MCP server (FastMCP migration,
aliases for legacy tool names, hardened HTTP transport with bearer-token
authentication and loopback-host guard).
