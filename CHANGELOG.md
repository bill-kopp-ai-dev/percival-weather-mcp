# Changelog

All notable changes to **percival-weather-mcp** are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
the project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- ``scripts/build_oci_label.py`` regenerates
  ``docs/mcp/percival-weather-mcp/oci-label.{json,yaml,inline}`` from the
  registry tools dump + a small fixed metadata block. Its ``--check`` flag
  is wired into ``tests/test_dockerfile.py`` as a CI gate so a hand-edit to
  the OCI label artifacts cannot drift past the regenerator.

### Fixed
- ``docs/tools.json`` was stale at ``version: "0.8.0"`` after the 0.9.0
  release; regenerated to ``"0.9.0"``.
- ``utils.get_closest_utc_index`` called ``dateutil.parser.isoparse(t)``
  twice for every timestamp (once for the naive-vs-aware check, once for
  the conversion). Extracted ``utils._parse_utc`` so each timestamp is
  parsed exactly once — a 50% reduction in parse overhead on hourly
  series.
- ``utils.format_air_quality_data`` called ``hourly.get("time", [])``
  twice in the same expression; cached the result so the list of times
  is only fetched once.

## [0.9.0] - 2026-09-24

### Added
- **Docker MCP Toolkit integration**. The image now declares the
  ``io.docker.server.metadata`` OCI label with a full
  ``catalog.ImportedServer`` payload so the Docker MCP Toolkit gateway
  can introspect the server without launching the container. The label
  payload is generated from ``docs/mcp/percival-weather-mcp/
  oci-label.json`` and embedded into the Dockerfile as a single-line
  ``LABEL`` instruction.
- **Registry-level manifest** under ``docs/mcp/percival-weather-mcp/
  server.yaml`` and ``tools.json``. Ready for the PR to
  ``docker/mcp-registry``; the PR itself is out of scope for this
  release (no ``mcp/`` Docker Hub namespace ownership yet).
- **POSIX-sh entrypoint** (``docker-entrypoint.sh``) that dispatches
  between transports: ``MCP_TRANSPORT`` wins when set, otherwise the
  first positional argument is the transport selector, otherwise
  ``stdio``. Forwards every other CLI flag through to ``python -m
  percival_weather_mcp``; enforces ``--host 0.0.0.0`` /
  ``--allow-remote-http`` when HTTP is requested.
- ``tool_export.build_registry_tools_document()`` and
  ``tool_export.registry_main()`` (the ``--registry`` CLI flag) emit the
  registry-friendly ``tools.json`` payload from the Pydantic schemas,
  collapsing ``Optional[list[X]]`` to ``type: array, items: {type: X}``.
- Conventional OCI labels (``org.opencontainers.image.*``) on the image
  for human inspection via ``docker inspect``.

### Changed
- The image **defaults to ``stdio``** so ``docker run -i --rm
  percival-weather-mcp`` Just Works as a drop-in backend for the
  Docker MCP Toolkit gateway, opencode and nanobot. HTTP is selected
  with ``MCP_TRANSPORT=http`` (or a trailing positional ``http`` arg).
- The image **no longer declares a HEALTHCHECK** at the Docker level.
  A HEALTHCHECK is resolved at build time and cannot adapt to the
  runtime transport — in stdio mode the container exits the moment
  stdin closes, so any HTTP probe would mark it unhealthy for the
  wrong reason. Operators running the HTTP transport add the
  HEALTHCHECK in their compose / k8s manifest (example in the
  Dockerfile comment block).
- ``tool_export.build_primitives_document()`` now also dumps
  ``weather_get_status`` so the embedded ``mcp.yaml`` and the
  registry ``tools.json`` line up with the actual server surface.
- The duplicate "Wire into OpenCode" / "Wire into the Docker MCP
  Toolkit" sections in the README were collapsed into one.

### Fixed
- ``docker-entrypoint.sh`` used to pass ``CMD ["stdio"]`` as a
  positional argument, producing ``python -m percival_weather_mcp
  --mode stdio stdio`` and an argparse "unrecognized arguments: stdio"
  error — the gateway spawn never started. The entrypoint now
  consumes the first positional as the transport selector.
- Tool proxies built by ``_make_tool_proxy`` leaked
  ``pydantic_core.PydanticUndefined`` into the rebuilt
  ``inspect.Parameter`` for fields declared with ``default_factory=``,
  which would later confuse ``func_metadata``. The proxy now resolves
  ``default_factory`` to its concrete value and keeps ``None`` defaults
  untouched.
- ``WeatherFormatter.format_current`` rendered upstream ``null`` values
  as the literal string ``"None"`` (for example "temperature of None°C")
  and crashed on ``None`` UV / visibility comparisons. Numeric sections
  now report ``"unavailable"`` when the upstream omits a value and the
  UV / visibility blocks are skipped entirely.
- ``MAX_CITY_NAME_LENGTH`` (120) disagreed with the Pydantic
  ``max_length=200`` declared on the weather input models. Bumped the
  runtime constant to 200 so a 121–200 character city flows through
  ``normalize_city_name`` instead of producing a misleading error after
  model validation.
- ``GetWeatherByDateRangeInput`` silently accepted an inverted range
  (``end_date`` before ``start_date``) and only failed at the service
  layer with a generic "Invalid weather request" message. A
  ``model_validator`` now rejects inverted ranges at the Pydantic level
  so the agent sees a clear, structured error before any HTTP call.

### Tests
- ``tests/test_dockerfile.py`` — lint the Dockerfile (image, syntax
  pragma, multistage, non-root, entrypoint, CMD, label presence).
- ``tests/test_entrypoint_script.py`` — behavioural tests for the
  entrypoint: positional vs env vs default transport, loopback host
  enforcement, no PATH hard-codes.
- ``tests/test_oci_label.py`` — schema check on the embedded
  ``io.docker.server.metadata`` label: required fields, forbidden
  fields, primitive-type argument restriction, parity with the
  registry ``tools.json``.
- ``tests/test_mcp_yaml.py`` — validate the embedded ``mcp.yaml``
  against the canonical ``docs/tools.json`` dump (catches the
  ``weather_get_status`` drop regression).
- ``tests/test_tool_export.py`` — pin ``build_primitives_document``
  includes the status tool and the registry payload has the right
  primitive types.
- Added ``tests/test_proxy_defaults.py`` to pin the default_factory /
  ``None``-default behaviour of ``_make_tool_proxy``.
- Added ``tests/test_formatter_none_handling.py`` to pin the
  "unavailable" rendering of the concise weather formatter.
- Added ``tests/test_date_range_validator.py`` to pin the Pydantic-level
  rejection of inverted date ranges.

## [0.8.0] - 2026-07-21

### Added
- `percival_weather_mcp.knowledge_base` module holding static reference
  tables — WMO weather codes, WHO/EPA air-quality bands, curated IANA
  timezones, and per-tool response schemas — exposed to the agent via
  MCP resources.
- Three MCP prompts (`weather_quick_answer`, `weather_analysis`,
  `weather_unit_conversion`) that bundle the recommended tool combinations
  and reference-table lookups for the three common workflow shapes.
- Three static MCP resources (`weather://codes`, `weather://aqi`,
  `weather://timezones`) and one resource template
  (`weather://schema/{tool_name}`) for on-demand reference data.
- `tool_export.build_primitives_document()` and `--mode export`-friendly
  tooling that serialises tools + prompts + resources + templates into
  `docs/tools.json`.
- New regression test modules: `test_primitives.py`,
  `test_docstring_quality.py`, `test_air_quality_integration.py`,
  `test_state_isolation.py`, `test_input_schema_fix.py`.

### Changed
- Every Pydantic input model now documents its description, examples,
  length/pattern constraints and defaults; the verbose "Output shape +
  Errors" prose moved into the tool description so the JSON schema does
  not duplicate it.
- `create_fastmcp_server()` no longer mutates the module-level
  `globals()["app"]`; each call returns a fresh, configured FastMCP
  instance. Tests and `tool_export` no longer leak registration state
  across invocations.
- `tool_export.build_primitives_document()` is now the canonical
  introspection surface; `build_tools_document()` is kept as a thin
  backwards-compatible alias.

### Fixed
- The eight data tools (`weather_get_*`, `weather_convert_time`,
  `weather_get_air_quality*`) used to expose `inputSchema = {"kwargs":
  {...}}` to MCP clients because the proxy function accepted bare
  `**kwargs`. A new `_make_tool_proxy` helper rebuilds the proxy's
  `__signature__` and `__annotations__` from `input_model.model_fields`,
  so FastMCP derives a per-field JSON schema. Resolves the bug reported
  in `MCP_Docs/Issues/2026-07-21-percival-weather-mcp-broken-input-schema.md`.
- `_call_handler` is now `async` and awaits `handler.run_tool` inside the
  metric context; `track_tool_async` exposes the real latency and
  exception type to Prometheus.
- `RateLimitMiddleware._buckets` now evicts idle entries every 60s
  (default idle-ttl 600s) to bound the dictionary size.
- `ResilientHttpClient.record_http_request` is called for **every**
  status code (including 4xx/5xx and retries), restoring error-path
  visibility in `mcp_weather_http_requests_total`.
- `_normalize_aq_variables` accepts any `Sequence[str]` (was `list` only).
- `ConvertTimeToolHandler` treats `"now"` case-insensitively and trims
  surrounding whitespace.

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
