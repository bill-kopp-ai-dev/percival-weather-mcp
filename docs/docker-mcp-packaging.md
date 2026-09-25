# Docker MCP packaging plan — `percival-weather-mcp` 0.9.0

## Goal

Repackage the FastMCP server as a Docker image that drops straight into
[opencode](https://github.com/anomalyco/opencode),
[nanobot](https://github.com/HKUDS/nanobot) and the
[Docker MCP Toolkit](https://docs.docker.com/ai/mcp-catalog-and-toolkit/toolkit/)
gateway without breaking the existing `uv run` / `python -m` workflows.

## Status (October 2026)

| Surface                      | Status before | Status after this plan |
|------------------------------|---------------|-----------------------|
| `uv run` / `python -m` stdio | works         | unchanged             |
| `uv run` HTTP / SSE          | works         | unchanged             |
| `docker run` HTTP (8080)     | works         | unchanged (legacy)    |
| `docker run` stdio (gateway) | broken        | **fixed**             |
| Docker MCP Toolkit catalog   | unsupported   | **fixed**             |
| OpenCode wiring              | documented    | verified              |
| Nanobot wiring               | documented    | verified              |
| `mcp.yaml` manifest          | missing       | **added** (label + file) |
| `server.yaml` registry entry | missing       | **added** (PR-ready)  |

## Why the current image is incompatible with the gateway

The 0.8.0 image hard-codes `streamable-http` as the default `CMD` and
never sets an `ENTRYPOINT`. The Docker MCP Toolkit gateway spawns each
catalog server as `docker run -i <image>` and expects the container to
speak MCP **over stdin/stdout** immediately. As shipped, the 0.8.0 image
starts a uvicorn HTTP server that ignores stdin, so the gateway never
receives the `initialize` handshake and the server silently fails its
health check.

A second regression in the in-progress Dockerfile: the entrypoint passed
`CMD ["stdio"]` as a positional argument (`"$@"`), so the FastMCP runner
received `python -m percival_weather_mcp --mode stdio stdio` and argparse
rejected the trailing `stdio`. That regression is fixed in commit dc7ddee
(Step 1) and re-pinned by `tests/test_entrypoint_script.py`.

## How the Docker MCP Toolkit discovers a server

> Research source: `docker/mcp-gateway` (commit on main, October 2026).

The Docker MCP Toolkit gateway **does not read `/mcp/mcp.yaml` from the
image filesystem**. It extracts the metadata from the **OCI image label**
`io.docker.server.metadata` (see `pkg/workingset/workingset.go:761-779`,
`getCatalogServerFromImage` in the gateway). The schema decoded from
that label is `catalog.ImportedServer`, a deliberately narrow subset of
the catalog-level `Server` schema.

That means a complete Docker MCP integration needs **three** files:

1. **OCI image label** `io.docker.server.metadata=<yaml>` — required for
   the gateway to consider the image a "self-describing server".
2. **`/mcp/mcp.yaml`** inside the image — informational. Useful for
   operators who `docker run --rm <image> cat /mcp/mcp.yaml` to inspect
   what the container exposes without launching it. Doubles as human
   documentation.
3. **`servers/percival-weather-mcp/server.yaml`** — the registry-level
   entry, submitted as a PR to `docker/mcp-registry` so the image
   becomes a first-class citizen of the [Docker MCP Catalog](https://hub.docker.com/mcp)
   and the in-Docker-Desktop catalog.

### Schema constraints (label-level)

The gateway enforces a stricter schema for the label:

- **Required fields** in the label: `name`, `type`, `tools[]`. The
  gateway rejects the image if any are missing — error: "image X is not
  a self-describing image".
- **Forbidden fields** in the label (silently dropped or rejected):
  `command`, `volumes`, `user`, `extraHosts`, `allowHosts`,
  `disableNetwork`, `longLived`, `sseEndpoint`, `remote.*`, `oauth.*`,
  `policy`, `secrets[]`, `env[].value`, `tools[].container.*`. These are
  reserved for trusted catalog/user config paths to avoid an image
  injecting arbitrary runtime decisions.
- **No `transport` field** at the label level. Transport is implicit from
  `type: server` (stdio). The image's `CMD` is what the gateway exec's.
- **No `prompts` / `resources` / `resourceTemplates`** in the manifest.
  Those are discovered at runtime through `prompts/list` and
  `resources/list` once the gateway connects. The image *should* expose
  them via the FastMCP server (and it does), but the manifest omits them.
- `env` entries in the label only carry `name`; values are resolved from
  user configuration or secrets at runtime.

### Catalog-level (`server.yaml`) — broader schema

The PR submitted to `docker/mcp-registry` includes a `server.yaml` that
follows the broader `catalog.Server` schema. That entry may declare
`image`, `secrets[]`, `run.env`, `config` blocks, and `meta.category` /
`meta.tags`. The Docker team reviews the PR, builds the image under
signing on the `mcp/` Docker Hub namespace, and the server becomes
available on hub.docker.com/mcp within 24 hours.

## Design

### Default transport

The image must default to `stdio` so `docker run -i …` Just Works. Users
who want the existing HTTP deployment will opt in via an env var
(`MCP_TRANSPORT=http`) or a positional argument (`docker run -i <image>
http`).

```bash
docker run -i --rm percival-weather-mcp            # stdio (gateway)
docker run -p 8080:8080 \
           -e MCP_TRANSPORT=http \
           percival-weather-mcp                    # HTTP (legacy)
docker run -p 8080:8080 \
           -e MCP_TRANSPORT=http-loopback \
           percival-weather-mcp                    # HTTP loopback (smoke)
```

### Entrypoint

A POSIX `sh` script (`docker-entrypoint.sh`) implements the dispatcher:

1. `MCP_TRANSPORT` wins when set.
2. Otherwise the first positional argument is treated as the transport
   selector (`docker run <image> http`).
3. Otherwise we default to `stdio`.

The script forwards every other CLI flag (`$@` minus the optional
selector) to `python -m percival_weather_mcp`. For HTTP modes the script
enforces `--host 0.0.0.0` / `--allow-remote-http` (or the loopback
variants) so operators cannot accidentally bind to a private interface.

### `mcp.yaml`

The file at `/mcp/mcp.yaml` is **human-readable documentation**; the
gateway ignores it but the file is useful for inspection and for
documentation. It documents the tools, prompts, resources and runtime
knobs in YAML. Format mirrors the field layout of the OCI label so an
operator can compare the two side-by-side.

### OCI label

The Dockerfile adds:

```dockerfile
LABEL io.docker.server.metadata="..."
```

with a JSON payload matching `catalog.ImportedServer` exactly. The
payload is regenerated from the registry tools dump + a small fixed
metadata block by [`scripts/build_oci_label.py`](../scripts/build_oci_label.py).
Run it whenever the tool surface or the project metadata changes:

```bash
uv run python -m percival_weather_mcp.tool_export --registry \
    > docs/mcp/percival-weather-mcp/tools.json
uv run python scripts/build_oci_label.py
```

The script writes `oci-label.json` (pretty source of truth),
`oci-label.yaml` (human-readable), and `oci-label.inline` (single-line
JSON copied verbatim into the Dockerfile `LABEL`). The
`scripts/build_oci_label.py --check` flag is wired into the test suite
as a CI gate so a hand-edit cannot drift past the regenerator.

### OpenCode wiring

OpenCode [configures local MCP servers](https://opencode.ai/docs/mcp-servers#local)
with `type: "local"` and a `command` array. The container spawn pattern
matches the gateway — `docker run -i --rm <image>` — and OpenCode
launches the container with stdin attached. The server replies over the
same channel, so the `-i` flag is mandatory.

```jsonc
// opencode.jsonc
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
      "environment": {
        "MCP_WEATHER_LOG_FORMAT": "json"
      },
      "enabled": true
    }
  }
}
```

### Nanobot wiring

Nanobot accepts the [standard MCP server config](https://github.com/HKUDS/nanobot)
under `tools.mcpServers`:

```jsonc
// ~/.nanobot/config.json
{
  "tools": {
    "mcpServers": {
      "percival-weather": {
        "command": "docker",
        "args": ["run", "-i", "--rm", "percival-weather-mcp:0.9.0"],
        "env": {
          "MCP_WEATHER_RATE_LIMIT_PER_MINUTE": "600"
        },
        "toolTimeout": 60
      }
    }
  }
}
```

### Docker MCP Toolkit integration

For a single-machine install via the Toolkit UI:

```bash
docker mcp profile create --name weather \
    --server docker://percival-weather-mcp:0.9.0
docker mcp client connect claude-code --profile weather  # or cursor, vscode, …
```

For an organization-wide catalog entry, submit `server.yaml` to
`docker/mcp-registry` via PR. Once approved, Docker builds the image
under signing, publishes it to the `mcp/` namespace on Docker Hub, and
the server becomes available in the [Docker MCP Catalog](https://hub.docker.com/mcp)
within 24 hours. Operators in the Docker Desktop catalog can then add it
to a profile with a checkbox.

## File-level changes

| File                            | Change                                                                 |
|---------------------------------|------------------------------------------------------------------------|
| `docker-entrypoint.sh`          | POSIX-sh dispatcher; consumes positional arg as transport selector     |
| `Dockerfile`                    | multistage; non-root user; OCI label `io.docker.server.metadata`; entrypoint + CMD ["stdio"]; copies entrypoint + mcp.yaml |
| `mcp.yaml`                      | embedded introspection document; kept in sync with the OCI label       |
| `scripts/build_oci_label.py`    | regenerates `oci-label.{json,yaml,inline}` from the registry tools dump + fixed project metadata; `--check` is a CI gate |
| `pyproject.toml`                | add `pyyaml>=6.0.3` to dev deps (validation in tests)                  |
| `.dockerignore`                 | exclude `.venv`, caches, `.positronic/`, `tests/`, secrets             |
| `docs/docker-mcp-packaging.md`  | this document                                                          |
| `docs/mcp/percival-weather-mcp/server.yaml` | registry-level manifest for the Docker MCP PR             |
| `docs/mcp/percival-weather-mcp/tools.json` | machine-readable tool list (required by registry)           |
| `docs/mcp/percival-weather-mcp/oci-label.{json,yaml,inline}` | generated by `scripts/build_oci_label.py`; inline form is embedded in the Dockerfile |
| `README.md`                     | document `docker run` (stdio + HTTP), opencode / nanobot wiring, Docker MCP Toolkit profile flow |
| `CHANGELOG.md`                  | new `[Unreleased]` / `## [0.9.0]` section                              |
| `tests/test_dockerfile.py`      | lint Dockerfile + entrypoint (image, label, ENTRYPOINT, CMD, etc.); asserts `scripts/build_oci_label.py --check` is green |
| `tests/test_entrypoint_script.py` | behavioural tests for entrypoint dispatch (positional, env, defaults) |
| `tests/test_mcp_yaml.py`        | validate `mcp.yaml` against `docs/tools.json`                          |
| `tests/test_oci_label.py`       | validate the Dockerfile's embedded `io.docker.server.metadata` label   |

## Verification (Smoke matrix)

| # | Command                                                                                     | Expected result                       |
|---|---------------------------------------------------------------------------------------------|---------------------------------------|
| 1 | `uv run pytest`                                                                             | all tests pass                        |
| 2 | `ruff check .` + `ruff format --check .` + `mypy src/`                                       | clean                                 |
| 3 | `docker build -t percival-weather-mcp:dev .`                                                | builds without error                  |
| 4 | `printf '{"jsonrpc":"2.0","id":1,"method":"initialize",...}\n{"jsonrpc":"2.0","method":"notifications/initialized",...}\n{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n' \| docker run -i --rm percival-weather-mcp:dev` | three JSON-RPC frames in stdout |
| 5 | `docker run --rm percival-weather-mcp:dev cat /mcp/mcp.yaml`                                | valid YAML (informational)            |
| 6 | `docker run --rm percival-weather-mcp:dev cat /etc/os-release`                              | Debian slim base                      |
| 7 | `docker run -d -e MCP_TRANSPORT=http -p 8080:8080 --name pw percival-weather-mcp:dev && curl -fsS http://127.0.0.1:8080/healthz && docker rm -f pw` | `{"status":"ok",...}`        |
| 8 | `docker image inspect --format '{{.Config.Labels}}' percival-weather-mcp:dev`               | contains `io.docker.server.metadata`  |
| 9 | `docker run -i --rm -e MCP_TRANSPORT=http percival-weather-mcp:dev < /dev/null`              | binds 0.0.0.0:8080                    |

After the smoke tests, `docker image inspect percival-weather-mcp:dev`
should show a final `USER` of `app`, no `root` user, and the OCI label.

## Out of scope

* OAuth-protected deployments — the server does not require auth for
  stdio. HTTP bearer-token auth keeps working as today.
* Multi-arch manifests (`linux/arm64`) — the Dockerfile uses
  `python:3.12-slim` which Docker Desktop pulls natively on both archs,
  but we are not adding an explicit `buildx` matrix.
* Pinning the Open-Meteo upstreams by IP — left to runtime retries and
  circuit breaker.
* Submitting `server.yaml` to `docker/mcp-registry` — the file is
  committed under `docs/mcp/percival-weather-mcp/server.yaml` so a
  future release can open the PR, but the PR itself is out of scope for
  this iteration (no Docker Hub namespace ownership).