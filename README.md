# percival-weather-mcp

MCP server for weather, air quality, and time tools, refactored for practical **Nanobot** usage and standardized with **uv + pyproject.toml + FastMCP**.

## Original Project (Reference)

This project is an evolution of the original repository:

- Original: [isdaniel/mcp_weather_server](https://github.com/isdaniel/mcp_weather_server)

Core functionality was preserved, while architecture, operational security, and agent integration were significantly improved.

## What Changed in This Refactor

### 1. Modern MCP Architecture
- Structural migration to **FastMCP** as the primary runtime.
- Tool registration through FastMCP public APIs.
- Unified transport support for:
  - `stdio` (default for local agents)
  - `sse`
  - `streamable-http`

### 2. More Stable Tool Contract for Agents
- Standardized tool names in `snake_case`.
- Backward-compatible alias for legacy calls (`get_weather_byDateTimeRange` -> `get_weather_by_datetime_range`).
- Improved docstrings and schema descriptions for better LLM understanding.

### 3. Better Response Design
- Clear separation between compact and detailed tools:
  - compact: optimized for agent reasoning
  - detailed: structured/raw JSON for automation pipelines

### 4. Performance and Robustness
- Explicit per-call HTTP timeouts.
- Shared HTTP client reuse in composed flows (for example: geocoding + air quality in the same call).
- TTL cache for geocoding to reduce repeated latency and API calls.

### 5. Operational Security
- Input sanitization and validation (city names, variables, dates, etc.).
- Safer remote HTTP execution:
  - remote bind blocked by default
  - token required for non-loopback exposure
  - support for `Authorization: Bearer` and `x-mcp-auth-token`

### 6. Packaging and Naming
- Distribution/project name: **`percival-weather-mcp`**.
- Canonical Python namespace: **`percival_weather_mcp`**.
- Backward compatibility layer preserved for legacy usage:
  - `python -m mcp_weather_server`
  - imports from `mcp_weather_server.*`

## Nanobot Optimization Highlights

This version is tuned for real Nanobot workflows:
(https://github.com/HKUDS/nanobot)

- `stdio`-first operation
- stable tool contract for consistent tool selection
- compact outputs to reduce token usage and tool-calling loops
- native support for `enabled_tools` and `tool_timeout`
- execution with a **shared root virtual environment** (no per-server `.venv`)

### Nanobot Configuration Example

In `config_ex.json`:

```json
"weather": {
  "command": "/home/<user>/.../percival.OS_Dev/.venv/bin/python",
  "args": ["-m", "percival_weather_mcp"],
  "enabled_tools": [
    "get_current_weather",
    "get_weather_by_datetime_range",
    "get_weather_details",
    "get_current_datetime",
    "get_timezone_info",
    "convert_time",
    "get_air_quality",
    "get_air_quality_details"
  ],
  "tool_timeout": 45
}
```

## Available Tools

### Weather
- `get_current_weather`
- `get_weather_by_datetime_range`
- `get_weather_details`

### Air Quality
- `get_air_quality`
- `get_air_quality_details`

### Time and Timezone
- `get_current_datetime`
- `get_timezone_info`
- `convert_time`

## Installation

### Requirements
- Python `>=3.10`
- `uv`

### Install in the project environment

```bash
cd mcp_servers/percival-weather-mcp
uv sync --dev
```

### Install in the shared workspace environment (recommended for Nanobot)

```bash
UV_CACHE_DIR=/tmp/uv-cache uv pip install \
  --python /home/<user>/.../percival.OS_Dev/.venv/bin/python \
  -e /home/<user>/.../percival.OS_Dev/mcp_servers/percival-weather-mcp
```

## Running

### Canonical namespace (recommended)

```bash
python -m percival_weather_mcp --mode stdio
```

With `uv`:

```bash
uv run -m percival_weather_mcp --mode stdio
```

### Legacy compatibility

```bash
python -m mcp_weather_server --mode stdio
```

## HTTP Modes

### SSE

```bash
python -m percival_weather_mcp --mode sse --host 127.0.0.1 --port 8080
```

### Streamable HTTP

```bash
python -m percival_weather_mcp --mode streamable-http --host 127.0.0.1 --port 8080
```

### Remote exposure (secured)

For non-loopback binding, both are required:
- `--allow-remote-http`
- auth token in environment (default: `MCP_WEATHER_AUTH_TOKEN`)

Example:

```bash
export MCP_WEATHER_AUTH_TOKEN="replace-this-token"
python -m percival_weather_mcp \
  --mode streamable-http \
  --host 0.0.0.0 \
  --port 8080 \
  --allow-remote-http
```

## Compatibility and Migration

If you are coming from the previous project/namespace:

- old `-m mcp_weather_server` still works
- new recommended form: `-m percival_weather_mcp`
- new script: `percival-weather-mcp`

Recommendation: migrate configs and automations gradually to the canonical namespace.

## Project Structure

```text
percival-weather-mcp/
├── pyproject.toml
├── uv.lock
└── src/
    ├── percival_weather_mcp/      # canonical namespace
    └── mcp_weather_server/        # compatibility layer
```

## Data Sources

- Weather/Forecast: [Open-Meteo](https://open-meteo.com/)
- Air Quality: [Open-Meteo Air Quality](https://open-meteo.com/en/docs/air-quality-api)

## License

Maintained according to the upstream project terms. See [LICENSE](./LICENSE).
