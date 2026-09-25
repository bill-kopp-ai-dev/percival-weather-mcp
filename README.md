# 🤖 Percival Weather - percival.OS MCP

**Version 0.9.0**

[![Python](https://img.shields.io/badge/python-3.10+-yellow.svg)]()
[![MCP](https://img.shields.io/badge/mcp-server-blue.svg)]()
[![percival.OS](https://img.shields.io/badge/percival.OS-ecosystem-orange.svg)](https://github.com/bill-kopp-ai-dev/percival.OS)

## 📋 Description

**Percival Weather** is the weather, air quality, and time MCP server for the
**percival.OS** ecosystem — a Personal Agentic Operating System designed for
autonomy, security, and absolute privacy. Version 0.8 hardens the resilience
layer (retries, circuit breaker, semaphore), introduces end-to-end
observability (Prometheus metrics, structured logs, health probes), adds
defensive middleware (per-IP rate limiting and bearer-token auth), ships the
Pydantic input contracts that power correct JSON schemas, and exposes the
server's reference tables through MCP **prompts** and **resources** so the
agent can choose the right tool and interpret the result without guesswork.

The server follows the [Model Context Protocol](https://modelcontextprotocol.io)
and uses FastMCP as the transport layer; it speaks `stdio`, `sse`, or
`streamable-http` interchangeably.

---

## 🛡️ percival.OS Principles

Like every component of `percival.OS`, this MCP server follows our core
principles:

- **Privacy & Transparency** — all weather and air-quality data comes from
  the open Open-Meteo APIs; no API keys or accounts are required for the
  server to start.
- **Data Sovereignty** — geocoding and forecast queries are processed
  on-the-fly and never logged beyond standard operational telemetry.
- **Hardened Security** — input sanitization and validation for every tool
  (city names, IANA timezones, ISO 8601 dates, pollutant lists), bearer-token
  auth for HTTP transports, and per-IP token-bucket rate limiting.
- **Agent-First Documentation** — every tool ships with a detailed
  description, output shape, error conditions, and worked examples, so the
  agent can self-serve.

---

## 🚀 Tools, Prompts, and Resources

The server exposes **9 tools**, **3 prompts**, **3 static resources**, and
**1 resource template**. A machine-readable snapshot is published to
[`docs/tools.json`](docs/tools.json).

### Weather & Forecast

| Tool | Description |
| --- | --- |
| `weather_get_current` | Concise prose snapshot (temperature, humidity, wind, pressure, UV, visibility). |
| `weather_get_by_range` | Statistics + hourly sample for an inclusive date range (max 16 days). |
| `weather_get_details` | All raw fields; optionally attach the next 24h of hourly forecast. |

### Air Quality

| Tool | Description |
| --- | --- |
| `weather_get_air_quality` | Current conditions, per-pollutant averages, and a compact hourly sample. |
| `weather_get_air_quality_details` | Full per-hour series for Open-Meteo air-quality fields. |

### Time & Timezone

| Tool | Description |
| --- | --- |
| `weather_get_time` | Current local datetime for an IANA timezone. |
| `weather_get_timezone` | UTC offset, DST flag, and timezone abbreviation. |
| `weather_convert_time` | Convert an ISO 8601 datetime (or `"now"`) between IANA timezones. |

### Status

| Tool | Description |
| --- | --- |
| `weather_get_status` | Liveness/readiness — name and version of the running server. |

### MCP Prompts (workflow recipes)

| Prompt | When to use it |
| --- | --- |
| `weather_quick_answer` | One-shot current-conditions question ("how is the weather in `<city>`?"). |
| `weather_analysis` | Range or multi-city analysis with averages, extremes, and comparisons. |
| `weather_unit_conversion` | Convert datetimes between IANA timezones. |

### MCP Resources (reference tables)

| URI | Content |
| --- | --- |
| `weather://codes` | WMO weather codes 0–99 with plain-English descriptions. |
| `weather://aqi` | Risk bands per pollutant following WHO 2021 / EPA breakpoints. |
| `weather://timezones` | Curated list of commonly-used IANA timezones. |
| `weather://schema/{tool_name}` | Top-level keys returned by the detailed tools. |

---

## ⚙️ Configuration

### Wire into Nanobot

Add the following entry under `tools.mcpServers` in your Nanobot config
(`~/.nanobot/config.json` or your project's `.nanobot/config.json`):

```json
{
  "tools": {
    "mcpServers": {
      "percival-weather-mcp": {
        "command": "uv",
        "args": [
          "run", "--project",
          "/path/to/percival-weather-mcp",
          "python", "-m", "percival_weather_mcp", "--mode", "stdio"
        ],
        "env": { "PYTHONUNBUFFERED": "1" },
        "toolTimeout": 60
      }
    }
  }
}
```

`uv run --project …` resolves the local venv automatically, so no manual
`pip install` is required at either location. After editing, run
`percival-weather-mcp_weather_get_current city="Lisbon, UK"` from the agent
to verify the wiring.

### Docker image

The official image (`percival-weather-mcp`) is published alongside every
release. It defaults to the **stdio** transport so it works as a drop-in
backend for the Docker MCP Toolkit gateway and for any MCP client that
launches it with `docker run -i --rm …`:

```bash
# Pull and run a single request (Docker MCP Toolkit gateway style)
docker run -i --rm percival-weather-mcp:0.9.0

# Smoke-test the /healthz probe in HTTP mode
docker run -d --name pw -p 8080:8080 \
    -e MCP_TRANSPORT=http \
    percival-weather-mcp:0.9.0
sleep 1 && curl -fsS http://127.0.0.1:8080/healthz && echo
docker rm -f pw
```

The image ships a POSIX-sh `docker-entrypoint.sh` that decodes the
`MCP_TRANSPORT` env var (`stdio`, `http`, or `http-loopback`) and forwards
every other CLI flag through to `python -m percival_weather_mcp`. A
static description of the server is embedded at `/mcp/mcp.yaml` so
`docker mcp catalog import` and similar introspection tools can read it
without launching the container.

### Wire into OpenCode

Add the container to `~/.config/opencode/opencode.json` (or a project's
`.opencode/opencode.json`) as a local MCP server:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "percival-weather": {
      "type": "local",
      "command": [
        "docker", "run", "-i", "--rm",
        "-e", "MCP_WEATHER_RATE_LIMIT_PER_MINUTE=600",
        "percival-weather-mcp:0.9.0"
      ],
      "enabled": true
    }
  }
}
```

OpenCode launches the container with stdin attached; the server replies
over the same channel, so the `-i` flag is required.

### Wire into the Docker MCP Toolkit

Add the image to a Toolkit profile. The image defaults to the stdio
transport, which is what the gateway expects:

```bash
docker mcp profile create --name weather \
    --server docker://percival-weather-mcp:0.9.0
docker mcp client connect claude-code --profile weather  # or cursor, vscode, …
```

The gateway introspects the image through the embedded `/mcp/mcp.yaml`
manifest, which documents the tools, prompts, resources, environment
variables and runtime knobs.

### HTTP transport

```bash
# Streamable HTTP with bearer token (recommended for production)
export MCP_WEATHER_AUTH_TOKEN="$(openssl rand -hex 32)"
percival-weather-mcp --mode streamable-http \
    --host 0.0.0.0 \
    --port 8080 \
    --allow-remote-http

# Optional: TLS directly (or front the server with Caddy / Nginx)
percival-weather-mcp --mode streamable-http \
    --host 0.0.0.0 --port 8443 \
    --allow-remote-http \
    --ssl-keyfile ./certs/key.pem \
    --ssl-certfile ./certs/cert.pem
```

`/healthz`, `/health`, and `/metrics` are exposed and bypass authentication
to integrate with orchestrators and load balancers.

### Environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `MCP_TRANSPORT` | `stdio` | Docker entrypoint transport selector (`stdio` / `http` / `http-loopback`). |
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
| `MCP_WEATHER_ENABLE_TRACING` | `false` | Enable OpenTelemetry tracing (requires the `[otel]` extra). |

---

## 🏗️ Architecture at a glance

```text
┌─────────────┐    JSON-RPC over stdio / SSE / HTTP    ┌────────────────┐
│ MCP client  │ ──────────────────────────────────────▶ │ FastMCP server │
└─────────────┘                                          └───────┬────────┘
                                                                   │
   ┌─────────────────── observability ───────────────────┐         │
   │  track_tool_async() → Prometheus + structured logs  │         │
   └─────────────────────────────────────────────────────┘         │
                                                                   ▼
   ┌──────────────────── middleware ────────────────────┐ ┌────────────────┐
   │ Bearer-token auth (outermost)                       │ │   Pydantic     │
   │  → RateLimitMiddleware (per-IP token bucket)       │ │   input models │
   └─────────────────────────────────────────────────────┘ └──────┬─────────┘
                                                                   ▼
                                                         ┌────────────────┐
                                                         │  ToolHandler   │
                                                         │   subclass     │
                                                         └──────┬─────────┘
                                                                ▼
                                                ┌──────────────────────────┐
                                                │  Weather / AQ / Time     │
                                                │  service + formatter     │
                                                └────────────┬─────────────┘
                                                             ▼
                                                ┌──────────────────────────┐
                                                │ ResilientHttpClient      │
                                                │  ├─ asyncio.Semaphore    │
                                                │  ├─ CircuitBreaker       │
                                                │  └─ Retry + Backoff      │
                                                └──────────────────────────┘
```

### What changed in 0.8

- **Reliability layer** — every outbound request goes through a
  `ResilientHttpClient` with bounded concurrency (`asyncio.Semaphore`),
  per-upstream circuit-breaker, and exponential backoff retries. Status
  5xx and 429 honour the retry policy.
- **Observability layer** — every tool call is wrapped in
  `track_tool_async` so the Prometheus counters
  `mcp_weather_tool_calls_total`, `mcp_weather_tool_errors_total`, and the
  `mcp_weather_tool_latency_seconds` histogram see the **real** execution
  time and exception type.
- **Security layer** — order-aware Starlette middleware stack:
  bearer-token auth runs before rate-limit so anonymous floods never
  consume rate budget; `RateLimitMiddleware._buckets` evicts idle entries
  every 60 s by default.
- **Agent contracts** — each Pydantic input model documents its
  description, examples, length/pattern constraints and defaults; the
  tool-level description includes the output shape and error conditions.
  `tool_proxy.__signature__` is reconstructed from
  `input_model.model_fields` so FastMCP derives a per-field JSON schema,
  not a single `kwargs` field (this is the bug referenced in
  `MCP_Docs/Issues/2026-07-21-percival-weather-mcp-broken-input-schema.md`).
- **Reference primitives** — `knowledge_base.py` holds WMO codes, AQI
  bands, curated IANA timezones, and per-tool response schemas; prompts
  teach the agent how to combine them.

---

## 🛠️ Development & Testing

This project uses [`uv`](https://docs.astral.sh/uv/) for dependency
management and `pytest` for tests.

```bash
# Install in your project's workspace
uv sync --project ./percival-weather-mcp

# Run the unit tests (respx mocks the Open-Meteo endpoints; no network required)
uv run --project ./percival-weather-mcp pytest

# Manual execution
uv run --project ./percival-weather-mcp python -m percival_weather_mcp --mode stdio
```

### Test layout

| File | Purpose |
| --- | --- |
| `tests/test_handlers.py` | Smoke tests for every tool handler. |
| `tests/test_http_client.py` | Resilient client, retries, breaker, and eviction. |
| `tests/test_middleware.py` | Rate-limit eviction, security headers, health probes. |
| `tests/test_server_metrics.py` | Regression: async `_call_handler` instrumentation. |
| `tests/test_state_isolation.py` | Regression: independent FastMCP instances. |
| `tests/test_input_schema_fix.py` | Regression: per-field JSON schema (no `kwargs`). |
| `tests/test_primitives.py` | List/read of prompts and resources. |
| `tests/test_docstring_quality.py` | Every tool exposes a rich description. |
| `tests/test_air_quality_integration.py` | End-to-end air-quality handlers. |

---

## 🔒 Security Notes

- HTTP transports require `--allow-remote-http` to bind to non-loopback
  hosts; without it the server refuses to start on `0.0.0.0` (defence-in-depth
  against accidental exposure).
- Set `MCP_WEATHER_AUTH_TOKEN` to a 32+ byte secret before enabling HTTP
  transports in any non-localhost setting. The same env-var name works on
  both sides of `--auth-token-env`.
- Health and metrics probes (`/healthz`, `/health`, `/metrics`) intentionally
  bypass the auth middleware so that orchestrators can scrape them without
  holding the token.

---

## 📚 About the Project

This server is an integral module of the **percival.OS** project. It provides
essential environmental data so that Nanobot can assist in decisions based on
weather and time.

- **Main Repository**: [https://github.com/bill-kopp-ai-dev/percival.OS](https://github.com/bill-kopp-ai-dev/percival.OS)
- **License**: MIT

---

*Developed with ❤️ by the percival.OS Team*
