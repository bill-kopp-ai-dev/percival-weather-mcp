# 🤖 Percival Weather - percival.OS MCP

**Version 0.7.0**

[![Python](https://img.shields.io/badge/python-3.10+-yellow.svg)]()
[![MCP](https://img.shields.io/badge/mcp-server-blue.svg)]()
[![percival.OS](https://img.shields.io/badge/percival.OS-ecosystem-orange.svg)](https://github.com/bill-kopp-ai-dev/percival.OS)

## 📋 Description
**Percival Weather** is an MCP server for weather, air quality, and time tools, refactored for practical Nanobot usage and standardized with **FastMCP**.

This server is part of the **percival.OS** ecosystem, a Personal Agentic Operating System designed for autonomy, security, and absolute privacy.

---

## 🛡️ percival.OS Principles
Like all components of `percival.OS`, this MCP server strictly follows our core principles:

- **Privacy & Transparency**: Weather queries are made via open APIs (Open-Meteo) without the need for invasive API keys or tracking.
- **Data Sovereignty**: Your location queries for weather forecasts are processed and presented only to you and your agent.
- **Hardened Security**: Input sanitization and validation (city names, variables, dates) to prevent malicious executions.
- **Transparency**: Based on the `isdaniel/mcp_weather_server` project, but with modernized architecture and deep integration with the Percival ecosystem.

---

## 🚀 Features & Tools

### Weather & Forecast
- `weather_get_current`: Get the current weather for a location.
- `weather_get_by_range`: Query history or forecasts by date range.
- `weather_get_details`: Detailed meteorological information.

### Air Quality
- `weather_get_air_quality`: Current air quality index.
- `weather_get_air_quality_details`: Breakdown of pollutants and metrics.

### Time & Timezone
- `weather_get_time`: Get local time from anywhere in the world.
- `weather_get_timezone`: Identify the timezone of coordinates or cities.
- `weather_convert_time`: Convert times between different timezones.

---

## ⚙️ Configuration in percival.OS (Nanobot)
Add the following configuration to your `~/.nanobot/config.json`:

```json
{
  "tools": {
    "mcpServers": {
      "weather": {
        "command": "/path/to/percival.OS_Dev/.venv/bin/python",
        "args": ["-m", "percival_weather_mcp"],
        "tool_timeout": 45
      }
    }
  }
}
```

### HTTP transport

```bash
# Streamable HTTP with bearer token (recommended for production)
export MCP_WEATHER_AUTH_TOKEN="$(openssl rand -hex 32)"
percival-weather-mcp --mode streamable-http \
    --host 0.0.0.0 \
    --port 8080 \
    --allow-remote-http

# Optional: enable TLS directly (or front the server with Caddy/Nginx)
percival-weather-mcp --mode streamable-http \
    --host 0.0.0.0 --port 8443 \
    --allow-remote-http \
    --ssl-keyfile ./certs/key.pem \
    --ssl-certfile ./certs/cert.pem
```

Health and metrics probes are exposed at `/healthz`, `/health` and
`/metrics` and bypass authentication to integrate with orchestrators.

### Environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `PORT` | `8080` | Listening port for HTTP transports. |
| `MCP_WEATHER_HOST` | `127.0.0.1` | Bind host. |
| `MCP_WEATHER_AUTH_TOKEN_ENV` | `MCP_WEATHER_AUTH_TOKEN` | Name of the env var holding the bearer token. |
| `MCP_WEATHER_HTTP_TIMEOUT` | `15.0` | Per-request timeout (seconds). |
| `MCP_WEATHER_HTTP_MAX_RETRIES` | `2` | Retry attempts beyond the first try. |
| `MCP_WEATHER_HTTP_BACKOFF_BASE` | `0.3` | Base delay (seconds) for exponential backoff. |
| `MCP_WEATHER_HTTP_BACKOFF_CAP` | `2.0` | Maximum delay (seconds) between retries. |
| `MCP_WEATHER_HTTP_MAX_CONCURRENCY` | `16` | Maximum in-flight outbound HTTP requests. |
| `MCP_WEATHER_RATE_LIMIT_PER_MINUTE` | `120` | Per-IP request budget. |
| `MCP_WEATHER_LOG_FORMAT` | `text` | `text` or `json`. |
| `MCP_WEATHER_ENABLE_METRICS` | `true` | Toggle Prometheus export. |
| `MCP_WEATHER_ENABLE_TRACING` | `false` | Enable OpenTelemetry tracing (requires `otel` extra). |

---

## 🛠️ Development & Testing
This project uses `uv` for dependency management.

```bash
# Installation in shared environment
uv pip install -e ./mcp_servers/percival-weather-mcp

# Manual execution
uv run -m percival_weather_mcp --mode stdio
```

---

## 📚 About the Project
This server is an integral module of the **percival.OS** project. It provides essential environmental data so that Nanobot can assist in decisions based on weather and time.

- **Main Repository**: [https://github.com/bill-kopp-ai-dev/percival.OS](https://github.com/bill-kopp-ai-dev/percival.OS)
- **License**: MIT

---
*Developed with ❤️ by the percival.OS Team*
