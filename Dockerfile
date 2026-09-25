# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /build
RUN pip install --no-cache-dir uv==0.5.7
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv export --format requirements-txt --no-hashes --no-dev > /tmp/requirements.txt \
 && uv venv /opt/venv \
 && uv pip install --python /opt/venv/bin/python -r /tmp/requirements.txt \
 && uv pip install --python /opt/venv/bin/python --no-deps .


FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:${PATH}" \
    MCP_TRANSPORT=stdio

RUN groupadd --system app && useradd --system --gid app --home /app app
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app pyproject.toml README.md LICENSE CHANGELOG.md ./
COPY --chown=app:app src ./src
COPY --chown=app:app docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
COPY --chown=app:app mcp.yaml /mcp/mcp.yaml
RUN chmod 0755 /usr/local/bin/docker-entrypoint.sh
USER app

EXPOSE 8080

# The image intentionally has no HEALTHCHECK at the Docker level: a
# HEALTHCHECK is resolved at build time and cannot adapt to the
# runtime transport. In stdio mode the container exits the moment
# stdin is closed, so any HTTP probe would mark it unhealthy for the
# wrong reason. Operators running the HTTP transport should add a
# HEALTHCHECK in their compose / k8s manifest:
#     HEALTHCHECK CMD ["python", "-c",
#         "import urllib.request, sys; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3)"]

# ---------------------------------------------------------------------------
# Docker MCP Toolkit metadata
# ---------------------------------------------------------------------------
#
# The Docker MCP Toolkit gateway (``docker/mcp-gateway``) discovers a server
# image by reading the OCI label ``io.docker.server.metadata`` from the image
# config — NOT a file inside the image. The label payload must match
# ``catalog.ImportedServer``: forbidden fields (command, volumes, user, etc.)
# are silently dropped by the gateway, and missing required fields cause the
# image to be rejected as "not a self-describing image".
#
# The single-line value below is generated from
# ``docs/mcp/percival-weather-mcp/oci-label.json``. Regenerate it with
# ``uv run python -m percival_weather_mcp.tool_export --registry > docs/mcp/percival-weather-mcp/tools.json``
# followed by ``uv run python scripts/build_oci_label.py`` (the helper at
# ``scripts/build_oci_label.py`` keeps the JSON, YAML and inline forms in
# sync). The script's ``--check`` flag is wired into the test suite as a
# CI gate so a hand-edit cannot drift past the regenerator. The literal is
# duplicated here so the image stays self-contained at build time and the
# gateway can introspect it without launching the container.
# ``tests/test_oci_label.py`` and ``tests/test_dockerfile.py`` assert that
# the embedded label matches the JSON source.
#
# A conventional label block follows for human operators inspecting the image
# (``docker inspect <image>``).
LABEL org.opencontainers.image.title="Percival Weather MCP" \
      org.opencontainers.image.description="Weather, air quality and time MCP server for the percival.OS ecosystem (Open-Meteo backed)" \
      org.opencontainers.image.source="https://github.com/bill-kopp-ai-dev/percival-weather-mcp" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.vendor="Positronic Bean Labs"

# io.docker.server.metadata is generated — see docs/mcp/percival-weather-mcp/oci-label.json
# fmt:off
LABEL io.docker.server.metadata="{\"name\": \"percival-weather-mcp\", \"type\": \"server\", \"title\": \"Percival Weather, Air Quality and Time\", \"description\": \"Weather, air quality and time MCP server for the percival.OS ecosystem. Backed entirely by the public Open-Meteo APIs (no API keys required). Nine tools, three prompts, three static resources and one resource template via FastMCP. Defaults to stdio so the Docker MCP Toolkit gateway spawns it drop-in.\", \"icon\": \"https://avatars.githubusercontent.com/u/182288589?s=200&v=4\", \"env\": [{\"name\": \"MCP_TRANSPORT\"}, {\"name\": \"PORT\"}, {\"name\": \"MCP_WEATHER_HOST\"}, {\"name\": \"MCP_WEATHER_AUTH_TOKEN_ENV\"}, {\"name\": \"MCP_WEATHER_HTTP_TIMEOUT\"}, {\"name\": \"MCP_WEATHER_HTTP_MAX_RETRIES\"}, {\"name\": \"MCP_WEATHER_HTTP_BACKOFF_BASE\"}, {\"name\": \"MCP_WEATHER_HTTP_BACKOFF_CAP\"}, {\"name\": \"MCP_WEATHER_HTTP_MAX_CONCURRENCY\"}, {\"name\": \"MCP_WEATHER_RATE_LIMIT_PER_MINUTE\"}, {\"name\": \"MCP_WEATHER_LOG_FORMAT\"}, {\"name\": \"MCP_WEATHER_ENABLE_METRICS\"}, {\"name\": \"MCP_WEATHER_ENABLE_TRACING\"}], \"tools\": [{\"name\": \"weather_convert_time\", \"description\": \"Convert a datetime from one timezone to another. Returns a JSON payload with the original and converted timestamps and the time difference in hours. Accepts 'now' or ISO 8601 input (including trailing 'Z').\", \"arguments\": [{\"name\": \"datetime_str\", \"type\": \"string\", \"desc\": \"Datetime to convert. Either the literal string 'now' (case-insensitive, whitespace allowed) or an ISO 8601 datetime (e.g. '2026-03-28T14:30:00', '2026-03-28T14:30:00Z', or '2026-03-28T14:30:00+02:00'). Strings without an offset are interpreted in ``from_timezone``.\", \"optional\": false}, {\"name\": \"from_timezone\", \"type\": \"string\", \"desc\": \"Source timezone (IANA name).\", \"optional\": false}, {\"name\": \"to_timezone\", \"type\": \"string\", \"desc\": \"Target timezone (IANA name).\", \"optional\": false}]}, {\"name\": \"weather_get_air_quality\", \"description\": \"Get compact air quality information for a city. Returns agent-friendly JSON text with current conditions, summary statistics, and a short hourly sample. Use this for concise analysis.\", \"arguments\": [{\"name\": \"city\", \"type\": \"string\", \"desc\": \"City name in English, optionally with region/country to disambiguate.\", \"optional\": false}, {\"name\": \"variables\", \"type\": \"array\", \"desc\": \"Optional subset of pollutant variables to query. If omitted, the default compact set is used: pm10, pm2_5, ozone, nitrogen_dioxide, carbon_monoxide. Pass an explicit list when the user asks for a specific pollutant (e.g. ['ozone']) or wants to exclude one.\", \"optional\": true, \"items\": {\"type\": \"string\"}}]}, {\"name\": \"weather_get_air_quality_details\", \"description\": \"Get detailed air quality data for a city as structured JSON text. Use this tool when downstream logic needs raw API-like fields in 'full_data'.\", \"arguments\": [{\"name\": \"city\", \"type\": \"string\", \"desc\": \"City name in English, optionally with region/country to disambiguate.\", \"optional\": false}, {\"name\": \"variables\", \"type\": \"array\", \"desc\": \"Optional pollutant list. If omitted, the extended default set is used: pm10, pm2_5, ozone, nitrogen_dioxide, carbon_monoxide, sulphur_dioxide, ammonia, dust, aerosol_optical_depth.\", \"optional\": true, \"items\": {\"type\": \"string\"}}]}, {\"name\": \"weather_get_by_range\", \"description\": \"Get weather data for a city between two calendar dates (inclusive). Returns a compact JSON payload optimized for agent analysis, including period metadata, summary statistics, and an hourly sample.\", \"arguments\": [{\"name\": \"city\", \"type\": \"string\", \"desc\": \"City name in English, optionally with region/country to disambiguate.\", \"optional\": false}, {\"name\": \"start_date\", \"type\": \"string\", \"desc\": \"Start date in ISO 8601 calendar format: YYYY-MM-DD. Must be on or before end_date.\", \"optional\": false}, {\"name\": \"end_date\", \"type\": \"string\", \"desc\": \"End date in ISO 8601 calendar format: YYYY-MM-DD (inclusive). The total range (end_date - start_date + 1) must be <= 16 days.\", \"optional\": false}]}, {\"name\": \"weather_get_current\", \"description\": \"Get a concise, human-readable snapshot of current weather for a city. Use this tool when you need a short summary (temperature, humidity, wind, precipitation context, pressure, clouds, UV, visibility), not raw datasets.\", \"arguments\": [{\"name\": \"city\", \"type\": \"string\", \"desc\": \"City name in English, optionally with region/country to disambiguate (for example: 'Springfield, US' or 'London, UK'). Control characters, angle brackets and excessive whitespace are stripped automatically.\", \"optional\": false}]}, {\"name\": \"weather_get_details\", \"description\": \"Get detailed structured JSON weather data for a city. Use this when you need raw fields for downstream processing. Optionally include a short forecast window.\", \"arguments\": [{\"name\": \"city\", \"type\": \"string\", \"desc\": \"City name in English, optionally with region/country to disambiguate.\", \"optional\": false}, {\"name\": \"include_forecast\", \"type\": \"boolean\", \"desc\": \"When true, attaches a 'forecast' array with the next 24 hours of hourly observations. Defaults to false for a smaller payload.\", \"optional\": true}]}, {\"name\": \"weather_get_time\", \"description\": \"Get the current local datetime for a specific IANA timezone. Returns structured JSON with timezone and ISO 8601 datetime.\", \"arguments\": [{\"name\": \"timezone_name\", \"type\": \"string\", \"desc\": \"IANA timezone name (for example: 'America/New_York', 'Europe/London', 'UTC'). Case-sensitive; must match the IANA database exactly. Refer to the ``weather://timezones`` resource for the curated list.\", \"optional\": false}]}, {\"name\": \"weather_get_timezone\", \"description\": \"Get timezone metadata for an IANA timezone as structured JSON: current local time, UTC time, offset in hours, DST flag, and timezone abbreviation. Use this when the user asks about DST, UTC offset, or abbreviation (e.g. 'PST', 'CET').\", \"arguments\": [{\"name\": \"timezone_name\", \"type\": \"string\", \"desc\": \"IANA timezone name (for example: 'America/Sao_Paulo', 'Asia/Tokyo'). Refer to ``weather://timezones`` for the curated list.\", \"optional\": false}]}, {\"name\": \"weather_get_status\", \"description\": \"Check the operational status of the weather server.\", \"arguments\": []}], \"metadata\": {\"category\": \"data\", \"tags\": [\"weather\", \"air-quality\", \"time\", \"timezone\", \"open-meteo\"], \"license\": \"MIT\", \"owner\": \"bill-kopp-ai-dev\"}}"
# fmt:on

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["stdio"]