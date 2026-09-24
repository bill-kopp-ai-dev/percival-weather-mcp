# Docker MCP packaging plan — `percival-weather-mcp` 0.9.0

## Goal

Repackage the FastMCP server as a Docker image that drops straight into
[opencode](https://github.com/anomalyco/opencode),
[nanobot](https://github.com/HKUDS/nanobot) and the
[Docker MCP Toolkit](https://docs.docker.com/ai/mcp-catalog-and-toolkit/toolkit/)
gateway without breaking the existing `uv run` / `python -m` workflows.

## Status (September 2026)

| Surface                      | Status before | Status after this plan |
|------------------------------|---------------|------------------------|
| `uv run` / `python -m` stdio | works         | unchanged              |
| `uv run` HTTP / SSE          | works         | unchanged              |
| `docker run` HTTP (8080)     | works         | unchanged (legacy)     |
| `docker run` stdio (gateway) | broken        | **fixed**              |
| Docker MCP Toolkit catalog   | unsupported   | **fixed**              |
| `mcp.yaml` manifest          | missing       | **added**              |

## Why the current image is incompatible with the gateway

The current `Dockerfile` hard-codes `streamable-http` as the default
`CMD` and never sets an `ENTRYPOINT`. The Docker MCP Toolkit gateway
spawns each catalog server as `docker run -i <image>` and expects the
container to speak MCP **over stdin/stdout** immediately. As shipped,
`docker run -i percival-weather-mcp` starts a uvicorn HTTP server that
ignores stdin, so the gateway never receives the `initialize` handshake
and the server silently fails its health check.

## Design

### Default transport

The image must default to `stdio` so `docker run -i …` Just Works. Users
who want the existing HTTP deployment will opt in via an env var
(`MCP_TRANSPORT=http`).

```
docker run -i --rm percival-weather-mcp            # stdio (gateway)
docker run -p 8080:8080 \
           -e MCP_TRANSPORT=http \
           --allow-remote-http=false \
           percival-weather-mcp                   # HTTP (legacy)
```

### Entrypoint

A small POSIX `sh` script (`docker-entrypoint.sh`) decodes the env var
and execs the right `python -m percival_weather_mcp --mode …` command,
preserving all the existing CLI flags. The script also short-circuits
the `/healthz` healthcheck in stdio mode (no HTTP listener → the probe
would fail and Docker would mark the container unhealthy).

### `mcp.yaml`

A registry-style manifest embedded in the image root so the Docker MCP
Toolkit gateway can introspect the server without spinning it up:

* `name`, `title`, `description`, `version`
* `transport` — defaults to `stdio`
* `command` / `args` — the exact `python -m …` invocation
* `tools` — auto-generated from `tool_export.build_primitives_document()`
* `env` — every documented runtime knob, with a default value where
  applicable

### Opencode wiring

```jsonc
// opencode.jsonc
{
  "mcp": {
    "percival-weather": {
      "type": "local",
      "command": [
        "docker", "run", "-i", "--rm",
        "-e", "MCP_WEATHER_RATE_LIMIT_PER_MINUTE=600",
        "ghcr.io/bill-kopp-ai-dev/percival-weather-mcp:0.8.0"
      ],
      "enabled": true
    }
  }
}
```

### Nanobot wiring

```jsonc
// ~/.nanobot/config.json
{
  "tools": {
    "mcpServers": {
      "percival-weather": {
        "command": "docker",
        "args": ["run", "-i", "--rm", "percival-weather-mcp:0.8.0"],
        "toolTimeout": 60
      }
    }
  }
}
```

### Docker MCP Toolkit catalog

* Add `server.yaml` under `servers/percival-weather-mcp/` of
  [docker/mcp-registry](https://github.com/docker/mcp-registry) so the
  catalog becomes available in Docker Desktop.
* Tag the image with the SemVer matching `pyproject.toml` plus the git
  short SHA (`0.8.0-abc1234`) so registry build provenance stays sane.

## File-level changes

| File                            | Change                                                                 |
|---------------------------------|------------------------------------------------------------------------|
| `docker-entrypoint.sh`          | **new** — POSIX sh entrypoint decoding `MCP_TRANSPORT`                 |
| `Dockerfile`                    | add `ENTRYPOINT`, default `CMD` to `["stdio"]`, copy entrypoint        |
| `mcp.yaml`                      | **new** — toolkit manifest, embedded in `/mcp/mcp.yaml`                |
| `.dockerignore`                 | make sure `docker-entrypoint.sh`, `mcp.yaml`, `docs/` are present      |
| `README.md`                     | document `docker run` (stdio + HTTP) and the toolkit profile           |
| `docs/docker-mcp-packaging.md`  | **new** — this plan, kept for future maintainers                       |
| `tests/test_dockerfile.py`      | **new** — lint the Dockerfile (base image, EXPOSE, ENTRYPOINT, CMD)     |
| `tests/test_mcp_yaml.py`        | **new** — validate `mcp.yaml` against the catalog schema               |
| `CHANGELOG.md`                  | add a `## [Unreleased]` entry once implementation lands                |

## Verification (Smoke matrix)

The following manual smoke tests must all pass before merging:

| # | Command                                                                                     | Expected result                       |
|---|---------------------------------------------------------------------------------------------|---------------------------------------|
| 1 | `docker build -t percival-weather-mcp:dev .`                                                | builds without error                  |
| 2 | `printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"smoke","version":"0.0.1"}}}\n{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}\n{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n' \| docker run -i --rm percival-weather-mcp:dev` | three JSON-RPC frames in stdout       |
| 3 | `docker run -d -e MCP_TRANSPORT=http -p 8080:8080 --name pw percival-weather-mcp:dev && curl -fsS http://127.0.0.1:8080/healthz && docker rm -f pw` | `{"status":"ok",...}`                  |
| 4 | `docker run -i --rm -e MCP_WEATHER_RATE_LIMIT_PER_MINUTE=1 percival-weather-mcp:dev < /dev/null` | exits non-zero when stdin is closed mid-handshake (acceptable) |

After the smoke tests, `docker image inspect percival-weather-mcp:dev`
should show a final USER of `app`, no `root` user, and a non-empty
`CMD`.

## Out of scope

* OAuth-protected deployments — the server does not require auth for
  stdio. HTTP bearer-token auth keeps working as today.
* Multi-arch manifests (`linux/arm64`) — the Dockerfile uses
  `python:3.12-slim` which Docker Desktop pulls natively on both archs,
  but we are not adding an explicit `buildx` matrix.
* Pinning the Open-Meteo upstreams by IP — left to runtime retries and
  circuit breaker.
