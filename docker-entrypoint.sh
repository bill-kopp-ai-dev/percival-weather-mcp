#!/bin/sh
# Docker entrypoint for percival-weather-mcp.
#
# Dispatches between transports:
#   * default (MCP_TRANSPORT unset and no positional arg) -> MCP over
#     stdin/stdout (Docker MCP Toolkit gateway, opencode, nanobot via
#     ``docker run -i …``).
#   * MCP_TRANSPORT=http or first arg "http"                 -> Streamable
#     HTTP on :8080, bound to 0.0.0.0 with --allow-remote-http.
#   * MCP_TRANSPORT=http-loopback or first arg "http-loopback" -> Streamable
#     HTTP on :8080, bound to 127.0.0.1 (no remote exposure).
#
# The script honours every flag accepted by
# ``python -m percival_weather_mcp``. When the HTTP transport is selected it
# enforces ``--host 0.0.0.0`` and ``--allow-remote-http`` so the operator
# cannot accidentally bind only to loopback inside a container.
#
# POSIX-sh only — no bash-isms so the script runs on Alpine-derived images
# and on the Debian slim base used in the Dockerfile.

set -eu

# Resolve the transport mode.
#
# 1. ``MCP_TRANSPORT`` env var wins when set (case-insensitive, trimmed).
# 2. The first positional argument, when it matches a recognised transport
#    (``stdio``/``http``/``http-loopback``), is consumed as the transport
#    selector even if ``MCP_TRANSPORT`` is also set — this keeps
#    ``CMD ["stdio"]`` from leaking into the Python argv when the gateway
#    spawns the image.
# 3. Otherwise we default to ``stdio`` — what the gateway expects.
transport="${MCP_TRANSPORT:-}"
if [ "$#" -gt 0 ]; then
    case "$1" in
        stdio|http|http-loopback)
            if [ -z "$transport" ]; then
                transport="$1"
            fi
            shift
            ;;
    esac
fi
transport=$(printf '%s' "$transport" | tr '[:upper:]' '[:lower:]' | tr -d ' ')
transport="${transport:-stdio}"

if [ "$transport" = "http" ] || [ "$transport" = "http-loopback" ]; then
    if [ "$transport" = "http-loopback" ]; then
        host="127.0.0.1"
        # ``--allow-remote-http`` is a store_true flag; the default is already
        # False, so we don't pass anything to keep argparse happy.
        allow_remote=""
    else
        host="0.0.0.0"
        allow_remote="--allow-remote-http"
    fi
    port="${PORT:-8080}"
    if [ -n "$allow_remote" ]; then
        exec python -m percival_weather_mcp \
            --mode streamable-http \
            --host "$host" \
            --port "$port" \
            "$allow_remote" \
            "$@"
    fi
    exec python -m percival_weather_mcp \
        --mode streamable-http \
        --host "$host" \
        --port "$port" \
        "$@"
fi

# Default: stdio. The gateway and any stdio-based client (opencode, nanobot,
# Claude Desktop, etc.) launches the container with ``-i`` attached, so we
# exec the FastMCP stdio runner with no extra positional arguments.
exec python -m percival_weather_mcp --mode stdio "$@"