# 🤖 Percival Weather — percival.OS MCP

**Version 0.10.0** · **Docker image is the primary distribution**

[![Python](https://img.shields.io/badge/python-3.10+-yellow.svg)]()
[![MCP](https://img.shields.io/badge/mcp-server-blue.svg)]()
[![percival.OS](https://img.shields.io/badge/percival.OS-ecosystem-orange.svg)](https://github.com/bill-kopp-ai-dev/percival.OS)

## 📋 Description

**Percival Weather** is the weather, air quality, and time MCP server for the
**percival.OS** ecosystem — a Personal Agentic Operating System designed for
autonomy, security, and absolute privacy.

This project belongs to Positronic Bean Labs (PBLabs), owned by Bill Kopp,
who is the sole final decision-maker for decisions requiring company approval.
Technical work and routine operations may be delegated; this does not authorize
publication or production changes. The company site, `labs.positronicbean.com`,
is under development and is not an operational service.

The server follows the [Model Context Protocol](https://modelcontextprotocol.io)
and uses FastMCP as the transport layer. It exposes **9 tools**, **3 prompts**,
**3 static resources** and **1 resource template**, backed entirely by the
public Open-Meteo APIs — no API keys, no accounts, no outbound credentials.

### Distribution: Docker first

**The supported and preferred way to run this server is the container image.**
The image defaults to the **stdio** transport, so a plain
`docker run -i --rm <image>` is a complete MCP server: it is what the Docker
MCP Toolkit gateway, OpenCode, Nanobot and the Positronic/Percival managers
launch, and it needs no Python toolchain, no `uv sync` and no host checkout.
HTTP is available as an opt-in mode of the same image.

Running from source with `uv run` is supported and is the path used by the
test suite, but it is a **development** path — see
[Running from source](#-running-from-source-development).

> **Publication status.** The image is currently **built and consumed
> locally**; it has not been published to a public registry. The planned
> destination is `docker.io/pbeanlabs`, with a release → digest → pull →
> index-PR flow. Until that happens, build the image locally with
> `scripts/docker-build.sh` and reference it by its local tag or image ID.
> See [docs/percival-integration-guide.md](docs/percival-integration-guide.md)
> for the distribution contract.

### Current release

**0.10.0** is a contract-level release: it fixes value and error defects
(WMO code 0, generic validation messages, empty air-quality variable lists),
adds qualifier-aware geocoding with explicit location identity and ambiguity
reporting, enforces a conservative forecast window, splits observed from
forecast model data with per-variable coverage counts, replaces concentration
risk labels with provider-computed US AQI subindices, and makes the hourly
sample selectable (`first` / `last` / `spread`). The full list is in
[CHANGELOG.md](CHANGELOG.md); the rationale and the verification evidence
behind each fix are recorded in the WX-RF implementation report, which is kept
as a local working record and is not published with the product.

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
  auth for HTTP transports, and per-IP token-bucket rate limiting. The
  container runs as a non-root user with a read-only root filesystem.
- **Agent-First Documentation** — every tool ships with a detailed
  description, output shape, error conditions, and worked examples, so the
  agent can self-serve.

---

## 🚀 Quick start — Docker (recommended)

```bash
# 1. Build the image from this checkout (reproducible: same commit → same image ID)
scripts/docker-build.sh percival-weather-mcp:0.10.0-dev

# 2. Run it as an MCP server over stdio (this is what a client launches)
docker run -i --rm --init percival-weather-mcp:0.10.0-dev

# 3. Smoke the HTTP profile in a throwaway container
docker run -d --name pw --init -p 127.0.0.1:8080:8080 \
    -e MCP_TRANSPORT=http \
    percival-weather-mcp:0.10.0-dev
sleep 1 && curl -fsS http://127.0.0.1:8080/healthz && echo
docker rm -f pw
```

Step 2 blocks on stdin: that is the MCP session. To drive it by hand, pipe
JSON-RPC frames in:

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"curl","version":"0.0.1"}}}' \
  '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | docker run -i --rm --init percival-weather-mcp:0.10.0-dev
```

Wire it into a client next: [OpenCode](#opencode),
[Nanobot](#nanobot) or the [Docker MCP Toolkit](#docker-mcp-toolkit).

---

## 🚀 Tools, Prompts, and Resources

A machine-readable snapshot with full JSON Schemas is published to
[`docs/tools.json`](docs/tools.json) and regenerated by
`python -m percival_weather_mcp.tool_export`.

### Weather & Forecast

| Tool | Description |
| --- | --- |
| `weather_get_current` | Concise prose snapshot (temperature, humidity, wind, precipitation context, pressure, clouds, UV, visibility) plus the nearest hourly model valid time in UTC. |
| `weather_get_by_range` | Statistics + hourly sample for an inclusive date range (default max 16 days). |
| `weather_get_details` | Structured JSON with all raw fields; optionally attaches the next 24 h of hourly forecast. |

### Air Quality

| Tool | Description |
| --- | --- |
| `weather_get_air_quality` | Current conditions, per-pollutant statistics, valid/missing coverage, provider-computed US AQI subindices and a compact hourly sample. |
| `weather_get_air_quality_details` | Full per-hour series for Open-Meteo air-quality fields; preserves every upstream array in `full_data`. |

### Time & Timezone

| Tool | Description |
| --- | --- |
| `weather_get_time` | Current local datetime for an IANA timezone. |
| `weather_get_timezone` | UTC offset, DST flag, and timezone abbreviation. |
| `weather_convert_time` | Convert an ISO 8601 datetime (or `"now"`) between IANA timezones. |

### Status

| Tool | Description |
| --- | --- |
| `weather_get_status` | Process liveness and server identity; upstream readiness is **not** checked. |

### MCP Prompts (workflow recipes)

| Prompt | When to use it |
| --- | --- |
| `weather_quick_answer` | One-shot current-conditions question ("how is the weather in `<city>`?"). |
| `weather_analysis` | Range or multi-city analysis with averages, extremes, and comparisons. |
| `weather_unit_conversion` | Convert datetimes between IANA timezones. |

### MCP Resources (reference tables)

| URI | Kind | Content |
| --- | --- | --- |
| `weather://codes` | static | WMO weather codes 0–99 with plain-English descriptions. |
| `weather://aqi` | static | Dimensionless US AQI categories, provider methods, units and limitations. |
| `weather://timezones` | static | Curated list of commonly-used IANA timezones. |
| `weather://schema/{tool_name}` | template | Generated output JSON Schema, keys and semantic notes for the detailed tools. |

The template accepts `weather_get_details`, `weather_get_by_range` and
`weather_get_air_quality_details`; any other name is a "resource not found"
error (`-32002`).

### Location, time and coverage contract (0.10.0)

- Queries retain their qualifiers: `London, UK`, `São Paulo, BR` and
  `Lisbon, Portugal`. Native region matches take precedence, including
  `Washington, D.C.` and `Springfield, IL`. A qualified failure never falls
  back to an unqualified city. At most two logical geocoder queries are made
  per cache miss, with the existing retry policy on each.
- Country fallback uses a bounded ISO-code/alias set, versioned in
  `tools/geocoding_service.py`: GB/UK/United Kingdom/Reino Unido,
  BR/Brazil/Brasil, FR/France/França, PT/Portugal, US/USA/United States/Estados Unidos,
  DE/Germany/Alemanha, JP/Japan/Japão, CA/Canada/Canadá, AU/Australia,
  ES/Spain/Espanha, IT/Italy/Italia/Itália, CN/China, IN/India/Índia and AR/Argentina.
  Other region qualifiers require a native identity match; arbitrary translations
  are not guaranteed. The short region aliases are IL, DC/D.C., NY and CA.
- JSON responses retain `city`, `latitude` and `longitude` (geocoded coordinates),
  adding `location` and `resolution`. Selection remains the first provider
  candidate, with up to three alternatives and a ten-result search limit;
  even one returned candidate is not proof of global uniqueness. The upstream
  model grid may differ from the geocoded coordinates.
- Current values select the nearest hourly model timestamp, which can be
  ahead of the clock. JSON includes `reference_time`, `valid_time` (weather),
  `selection_method` and UTC context; prose includes the model valid time.
  Past timestamps are **not evidence of measured station observations**.
- Range policy is **UTC today minus 92 days through today plus 15 days**,
  inclusive, for at most 16 consecutive days by default. Requests outside this
  policy fail locally with the actual allowed dates. This tool does not query
  the Archive API. Calendar examples must be adjusted to the current window.
- `summary_scope="entire_returned_window"` preserves whole-window summaries;
  `coverage` gives valid/missing counts per variable and statistics separately
  for `past_or_present` and `future`. Short arrays and nulls remain missing;
  booleans/non-finite values are not numeric measurements. Empty statistics
  are null, not zero. Precipitation has min/max/avg, not an accumulated total.
- Range `sample_mode` is optional: `first` (default), `last` or `spread`, up to
  **12** ordered rows. `spread` includes both endpoints. AQ compact samples
  retain at most **8** rows. `sample` reports the limit, total and truncation;
  a sample is not the complete time series.
- `variables=[]` is invalid for both AQ tools; omission/null uses the existing
  defaults. A fully missing requested pollutant series is a no-data error.
  AQ subindices are requested in the same API call for supported pollutants:
  `air_quality_index` classifies **provider-computed US AQI**, never raw hourly
  mass concentrations. Only requested pollutant subindices are represented;
  no partial maximum is called a global AQI. Ammonia/dust/AOD have no supported
  index. Unavailable indices never mean "Good". Consult `weather://aqi`.
- JSON text is compact UTF-8 and rejects NaN/Infinity. AQ details preserve
  **all** returned `full_data` keys/arrays, including unknown provider fields;
  payload size grows with hours × variables, without hidden truncation. The
  deterministic 120h × 9-pollutant fixture (plus supported subindices and all
  metadata) measures **14,378 bytes compact vs 35,232 indented**, a 59.2%
  reduction for the same decoded object; its regression budget is 16 KiB.

Weather data: [Open-Meteo Forecast API](https://open-meteo.com/en/docs).
Air quality: [Open-Meteo / CAMS ENSEMBLE](https://open-meteo.com/en/docs/air-quality-api).
US AQI categories are distinct from WHO concentration guidelines and do not
claim equivalence to a Brazilian regulatory index or an independent audit of
the provider's algorithm. HTTP `/health` and `/healthz` also express liveness.

---

## 🐳 The Docker image

### What is inside

| Property | Value |
| --- | --- |
| Default transport | `stdio` (`CMD ["stdio"]`) |
| Entry point | POSIX-sh `docker-entrypoint.sh`, dispatching `stdio` / `http` / `http-loopback` |
| Runtime user | `app` (non-root) |
| Base image | `debian:forky-slim` (pinned by digest), Python 3.12 runtime |
| Introspection | OCI label `io.docker.server.metadata` + embedded `/mcp/mcp.yaml` |
| Reproducible build | version, revision and timestamp derived from the checkout |

`scripts/docker-build.sh` is the documented build path: it reads the version
from `pyproject.toml`, the revision from `git rev-parse HEAD` and the build
timestamp from the commit date, and passes them as build arguments so the
OCI labels carry a real `version`/`revision` pair. It also pins the layer
timestamps and drops the build-time attestation, so **two builds of the same
commit produce the same image ID**. A bare `docker build -t … .` still
works, but it leaves `version=0.0.0` / `revision=unknown` in the labels and
does not produce a reproducible image.

```bash
scripts/docker-build.sh                                     # tag: percival-weather-mcp:dev
scripts/docker-build.sh percival-weather-mcp:0.10.0         # a pinned candidate tag
scripts/docker-build.sh percival-weather-mcp:ci --no-cache  # clean rebuild
```

### Transports

The transport is selected by `MCP_TRANSPORT` (or by a trailing positional
argument). An unknown value is refused with exit code 2 instead of silently
degrading to stdio.

```bash
docker run -i --rm --init percival-weather-mcp:0.10.0-dev                # stdio (default)
docker run -i --rm --init -e MCP_TRANSPORT=http-loopback …               # HTTP bound to 127.0.0.1
docker run --rm -p 127.0.0.1:8080:8080 -e MCP_TRANSPORT=http …           # HTTP bound to 0.0.0.0
```

In `http` mode the entrypoint enforces `--host 0.0.0.0 --allow-remote-http`
so an operator cannot accidentally publish a loopback-only service; in
`http-loopback` it binds `127.0.0.1` and does not require that flag. Every
other CLI flag is forwarded to `python -m percival_weather_mcp`.

### Pinning

For reproducible deployments, pin the image by version or, preferably, by
digest:

```bash
# by version tag
docker run -i --rm --init percival-weather-mcp:0.10.0

# by digest (survives tag moves) — available once the image is published
docker run -i --rm --init pbeanlabs/percival-weather-mcp@sha256:<digest>
```

The `:latest` tag is a convenience for local iteration; production
deployments should pin an immutable reference.

### Docker Compose

`docker-compose.yml` ships two services for local development and fixtures:
a stdio service (always available) and an HTTP service behind the `http`
profile.

```bash
# stdio service (the default shape of a manager-managed deployment)
docker compose run --rm -T percival-weather-stdio

# HTTP profile — loopback bind, bearer token from a file-backed secret
docker compose --profile http up --build
```

The HTTP profile expects a token file at
`${MCP_WEATHER_AUTH_TOKEN_FILE:-${HOME}/.config/percival/weather_auth_token}`,
readable by UID 999, and publishes the port on `127.0.0.1` only.

### Introspection metadata

The gateway discovers the server through the **OCI label**
`io.docker.server.metadata`, which must match the narrower
`catalog.ImportedServer` schema (`name`, `type` and `tools[]` are required;
`command`, `volumes`, `user` and other runtime-shaping fields are dropped by
the gateway). The label is generated from the registry tools dump:

```bash
uv run python -m percival_weather_mcp.tool_export --registry \
    > docs/mcp/percival-weather-mcp/tools.json
uv run python scripts/build_oci_label.py          # writes oci-label.{json,yaml,inline}
uv run python scripts/build_oci_label.py --check  # CI gate: fails on drift
```

The file embedded at `/mcp/mcp.yaml` is **informational**: it mirrors the
label's field layout so an operator can read the surface without launching
the container (`docker run --rm <image> cat /mcp/mcp.yaml`). The gateway does
not read it.

---

## ⚙️ Configuration

### Environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `MCP_TRANSPORT` | `stdio` | Docker entrypoint transport selector (`stdio` / `http` / `http-loopback`). |
| `PORT` | `8080` | Listening port for HTTP transports (`MCP_WEATHER_PORT` is the fallback). |
| `MCP_WEATHER_HOST` | `127.0.0.1` | Bind host for the HTTP transports. |
| `MCP_WEATHER_AUTH_TOKEN_ENV` | `MCP_WEATHER_AUTH_TOKEN` | Name of the env var holding the bearer token. |
| `MCP_WEATHER_AUTH_TOKEN` | — | The bearer token itself. Unset means HTTP auth is not enforced. |
| `MCP_WEATHER_HTTP_TIMEOUT` | `15.0` | Per-request timeout (seconds). |
| `MCP_WEATHER_HTTP_MAX_RETRIES` | `2` | Retry attempts beyond the first try (max 10). |
| `MCP_WEATHER_HTTP_BACKOFF_BASE` | `0.3` | Base delay (seconds) for exponential backoff. |
| `MCP_WEATHER_HTTP_BACKOFF_CAP` | `2.0` | Maximum delay (seconds) between retries. |
| `MCP_WEATHER_HTTP_MAX_CONCURRENCY` | `16` | Maximum in-flight outbound HTTP requests. |
| `MCP_WEATHER_RATE_LIMIT_PER_MINUTE` | `120` | Per-IP request budget on HTTP transports. |
| `MCP_WEATHER_LOG_FORMAT` | `text` | `text` or `json`. |
| `MCP_WEATHER_ENABLE_METRICS` | `true` | Toggle Prometheus export. |
| `MCP_WEATHER_ENABLE_TRACING` | `false` | Enable OpenTelemetry tracing (requires the `[otel]` extra). |

Out-of-range values (`PORT`, timeout, retries, concurrency, rate limit) are
refused at start-up with an operator message and a non-zero exit, instead of
being silently clamped.

### CLI flags

Available when running the server directly (`python -m percival_weather_mcp`
or the `percival-weather-mcp` console script):

| Flag | Default | Description |
| --- | --- | --- |
| `--mode` | `stdio` | `stdio`, `sse` or `streamable-http`. |
| `--host` | `127.0.0.1` | Bind host (HTTP modes only). |
| `--port` | `PORT` / `8080` | Listening port (HTTP modes only). |
| `--allow-remote-http` | off | Required to bind an HTTP transport to a non-loopback host. |
| `--stateless` | off | Stateless session handling (streamable-http only). |
| `--auth-token-env` | `MCP_WEATHER_AUTH_TOKEN` | Name of the env var carrying the bearer token. |
| `--ssl-keyfile` / `--ssl-certfile` | — | PEM key/certificate for TLS termination in the server. |
| `--debug` | off | Debug logging. |

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

`/healthz` and `/health` are exposed and bypass authentication to integrate
with orchestrators and load balancers. `/metrics` carries operational
counters and therefore **requires the same bearer token** as the rest of the
HTTP surface (when a token is configured) — see the
[decision record](docs/decisions/2026-10-28-http-endpoint-auth-policy.md).

---

## 🔌 Client wiring

### OpenCode

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
        "percival-weather-mcp:0.10.0"
      ],
      "timeout": 120000,
      "enabled": true
    }
  }
}
```

OpenCode launches the container with stdin attached; the server replies
over the same channel, so the `-i` flag is required.

The optional `timeout` field (`ms`, default `5000`) caps each `tools/call`
round-trip — a single weather lookup can chain a geocoding request plus the
forecast request, so 30 s–2 min is recommended. Bump further (or pair with
`MCP_WEATHER_HTTP_TIMEOUT` on the container) when the upstream Open-Meteo APIs
are degraded.

### Nanobot

Add the following entry under `tools.mcpServers` in your Nanobot config
(`~/.nanobot/config.json` or your project's `.nanobot/config.json`):

```json
{
  "tools": {
    "mcpServers": {
      "percival-weather-mcp": {
        "command": "docker",
        "args": [
          "run", "-i", "--rm",
          "percival-weather-mcp:0.10.0"
        ],
        "env": { "MCP_WEATHER_RATE_LIMIT_PER_MINUTE": "600" },
        "toolTimeout": 120
      }
    }
  }
}
```

`toolTimeout` (seconds) caps each `tools/call` round-trip. The default 60 s is
tight for this codebase — a single `weather_get_by_range` call issues 1
geocoding request plus 16 days of hourly data, and `MCP_WEATHER_HTTP_TIMEOUT`
retries the chain with exponential backoff (up to ~2 s per attempt). `90`–`120`
seconds is recommended; raise further if the upstream Open-Meteo APIs are
degraded.

### Docker MCP Toolkit

Add the image to a Toolkit profile. The image defaults to the stdio
transport, which is what the gateway expects:

```bash
docker mcp profile create --name weather \
    --server docker://percival-weather-mcp:0.10.0
docker mcp client connect claude-code --profile weather  # or cursor, vscode, …
```

The Docker MCP Toolkit gateway launches each server with a fixed
resource envelope (`--cpus 1 --memory 2Gb --security-opt no-new-privileges`).
For stdio the upstream Open-Meteo traffic is tiny, so the defaults are
generous; for HTTP behind the gateway, raise
`MCP_WEATHER_RATE_LIMIT_PER_MINUTE` (default `120`) per profile to
absorb concurrent clients, or pin the image to a specific version tag
to avoid surprise upgrades.

---

## ▶️ Running from source (development)

This path exists for development and for the test suite. It is **not** the
recommended deployment form.

```bash
# Install in your project's workspace
uv sync --project ./percival-weather-mcp

# Run the unit tests (respx mocks the Open-Meteo endpoints; no network required)
uv run --project ./percival-weather-mcp pytest

# Manual execution
uv run --project ./percival-weather-mcp python -m percival_weather_mcp --mode stdio
```

Source-based consumers (Nanobot and others) accept the standard MCP server
config:

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
        "toolTimeout": 120
      }
    }
  }
}
```

`uv run --project …` resolves the local venv automatically, so no manual
`pip install` is required at either location. After editing, call
`weather_get_current city="Lisbon, Portugal"` from the agent to verify the
wiring.

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

Every tool call is wrapped in `track_tool_async`, so the Prometheus counters
`mcp_weather_tool_calls_total`, `mcp_weather_tool_errors_total` and the
`mcp_weather_tool_latency_seconds` histogram see the **real** execution time
and exception type. Outbound requests go through a `ResilientHttpClient` with
bounded concurrency (`asyncio.Semaphore`), a per-upstream circuit breaker and
exponential backoff: 5xx and 429 honour the retry policy, non-recoverable 4xx
do not.

The Starlette middleware stack is order-aware: bearer-token auth runs before
the rate limiter, so anonymous floods never consume rate budget.

Each tool's JSON Schema is derived from its Pydantic input model —
`tool_proxy.__signature__` is reconstructed from `input_model.model_fields`, so
FastMCP publishes a per-field schema instead of a single `kwargs` field.

---

## 🛠️ Development & Testing

This project uses [`uv`](https://docs.astral.sh/uv/) for dependency
management and `pytest` for tests.

```bash
uv sync --project ./percival-weather-mcp     # install
uv run --project ./percival-weather-mcp pytest                  # unit tests (no network)
uv run --project ./percival-weather-mcp ruff check .             # lint
uv run --project ./percival-weather-mcp ruff format --check .   # formatting
uv run --project ./percival-weather-mcp mypy src/percival_weather_mcp
```

### Test layout

| Area | Files |
| --- | --- |
| Handlers and formatters | `test_handlers.py`, `test_formatters.py`, `test_formatter_none_handling.py` |
| Resilient HTTP client, retries, breaker | `test_http_client.py`, `test_error_taxonomy.py`, `test_proxy_defaults.py` |
| Middleware, auth and metrics | `test_middleware.py`, `test_metrics_auth.py`, `test_server_metrics.py` |
| Geocoding identity, qualifiers and cache | `test_geocoding_resolution.py`, `test_geocoding_cache.py` |
| Functional contracts (values, coverage, sample, payload) | `test_functional_values_validation.py`, `test_functional_wire_contract.py`, `test_series.py`, `test_payload_budget.py`, `test_range_policy.py`, `test_date_range_validator.py` |
| MCP surface (schemas, wire, primitives, prompts/resources) | `test_tool_schemas.py`, `test_input_schema_fix.py`, `test_mcp_wire_contract.py`, `test_primitives.py`, `test_tool_export.py`, `test_docstring_quality.py` |
| Air quality and US AQI | `test_air_quality_integration.py`, `test_air_quality_index.py` |
| Container and packaging metadata | `test_dockerfile.py`, `test_entrypoint_script.py`, `test_mcp_yaml.py`, `test_oci_label.py`, `test_catalog_metadata.py` |
| Lifecycle and configuration | `test_lifecycle_signals.py`, `test_config_validation.py`, `test_state_isolation.py` |

Container-level checks live outside the unit suite: `scripts/smoke-container.sh`
(smoke against a local image) and `scripts/docker-ci-conformance.py`
(hermetic stdio conformance, `--network=none`). CI
(`.github/workflows/ci.yml`) runs lint, types and tests on Python 3.10–3.12,
then builds the image, scans it with Trivy and exercises the Compose contracts.

---

## 🔒 Security Notes

- HTTP transports require `--allow-remote-http` to bind to non-loopback
  hosts; without it the server refuses to start on `0.0.0.0` (defence-in-depth
  against accidental exposure).
- Set `MCP_WEATHER_AUTH_TOKEN` to a 32+ byte secret before enabling HTTP
  transports in any non-localhost setting. The same env-var name works on
  both sides of `--auth-token-env`.
- Health probes (`/healthz`, `/health`) intentionally bypass the auth
  middleware so that orchestrators can reach them without holding the token.
  `/metrics` does **not** bypass it: it exposes operational counters and
  requires the bearer token whenever one is configured.
- The container runs as the non-root `app` user, drops all capabilities and
  ships with a read-only root filesystem in the Compose profile.
- `MCP_WEATHER_AUTH_TOKEN` is an environment variable and must never be baked
  into a published image or committed to a profile.

---

## 📚 Documentation

| Document | What it answers |
| --- | --- |
| [docs/README.md](docs/README.md) | Index of this documentation tree and what is canonical. |
| [docs/percival-integration-guide.md](docs/percival-integration-guide.md) | Runtime profile and distribution contract for the Percival consumer. |
| [docs/decisions/2026-10-28-http-endpoint-auth-policy.md](docs/decisions/2026-10-28-http-endpoint-auth-policy.md) | Why `/healthz` is open and `/metrics` requires the bearer token. |
| [docs/security/README.md](docs/security/README.md) | Vulnerability disposition and scan evidence for the current candidate. |
| [docs/tools.json](docs/tools.json) | Machine-readable snapshot of tools, prompts and resources. |
| [CHANGELOG.md](CHANGELOG.md) | Release-by-release changes. |

---

## 📚 About the Project

This server is an integral module of the **percival.OS** project. It provides
essential environmental data so that Nanobot can assist in decisions based on
weather and time.

- **Main Repository**: [https://github.com/bill-kopp-ai-dev/percival.OS](https://github.com/bill-kopp-ai-dev/percival.OS)
- **License**: MIT

---

*Developed with ❤️ by the percival.OS Team*
