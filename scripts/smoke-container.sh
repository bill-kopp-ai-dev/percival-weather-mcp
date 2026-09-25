#!/usr/bin/env bash
# Smoke test for percival-weather-mcp:dev
#
# Verifies the contract documented in docs/docker-mcp-packaging.md:
#   1. Container default transport is stdio (gateway mode).
#   2. The MCP handshake round-trips: initialize -> tools/list.
#   3. MCP_TRANSPORT=http binds 0.0.0.0:8080 and serves /healthz
#      when MCP_WEATHER_AUTH_TOKEN is set.
#   4. MCP_TRANSPORT=http-loopback binds 127.0.0.1:8080 and serves
#      /healthz with no token (intentional).
#   5. The OCI label io.docker.server.metadata parses as JSON with the
#      tools advertised by the FastMCP server (gateway contract).
#   6. The container runs as the non-root user "app".
#   7. The embedded /mcp/mcp.yaml is a valid YAML document.
#
# Requires: docker, curl, python3 (for json/yaml parsing), and a working
# image tagged percival-weather-mcp:dev.

set -euo pipefail

IMAGE=${IMAGE:-percival-weather-mcp:dev}

fail() {
    printf '\033[31m[FAIL]\033[0m %s\n' "$1" >&2
    exit 1
}

pass() {
    printf '\033[32m[ ok ]\033[0m %s\n' "$1"
}

info() {
    printf '\033[36m[info]\033[0m %s\n' "$1"
}

require_image() {
    if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
        fail "image $IMAGE is missing — run 'docker build -t $IMAGE .' first"
    fi
}

# ---------------------------------------------------------------------------
# 1-2. stdio gateway mode
# ---------------------------------------------------------------------------

test_stdio_gateway() {
    info "stdio gateway mode (docker run -i --rm)"
    local payload
    payload=$(
        printf '%s\n' \
            '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"smoke","version":"0.0.1"}}}' \
            '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}' \
            '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' |
            docker run -i --rm "$IMAGE" 2>/dev/null
    )
    local initialize_reply tools_reply
    initialize_reply=$(printf '%s' "$payload" | sed -n '1p')
    tools_reply=$(printf '%s' "$payload" | sed -n '2p')
    if ! printf '%s' "$initialize_reply" | grep -q '"serverInfo":{"name":"percival-weather-mcp"'; then
        fail "stdio mode: initialize reply is missing serverInfo"
    fi
    pass "stdio mode: handshake round-trip OK"

    # Every advertised tool must surface in tools/list.
    for tool in \
        weather_get_current \
        weather_get_by_range \
        weather_get_details \
        weather_get_air_quality \
        weather_get_air_quality_details \
        weather_get_time \
        weather_get_timezone \
        weather_convert_time \
        weather_get_status ; do
        if ! printf '%s' "$tools_reply" | grep -q "\"name\":\"$tool\""; then
            fail "stdio mode: tools/list missing '$tool'"
        fi
    done
    pass "stdio mode: all 9 tools present in tools/list"
}

# ---------------------------------------------------------------------------
# 3. HTTP transport with auth token
# ---------------------------------------------------------------------------

test_http_transport() {
    info "HTTP transport with bearer token"
    local token container
    token="smoketest12345678901234567890123456789012"
    container=$(docker run -d --rm \
        -e MCP_TRANSPORT=http \
        -e "MCP_WEATHER_AUTH_TOKEN=$token" \
        -p 8080:8080 \
        --name pw-http \
        "$IMAGE")
    trap 'docker rm -f pw-http >/dev/null 2>&1 || true' RETURN

    # Wait up to 5s for the listener to come up.
    local body
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        if body=$(curl -fsS http://127.0.0.1:8080/healthz 2>/dev/null); then
            break
        fi
        sleep 0.5
    done
    if [[ -z "${body:-}" ]]; then
        docker logs "$container" >&2 || true
        fail "HTTP mode: /healthz never became reachable"
    fi
    if ! printf '%s' "$body" | grep -q '"status":"ok"'; then
        fail "HTTP mode: /healthz returned '$body'"
    fi
    if ! printf '%s' "$body" | grep -q '"server":"percival-weather-mcp"'; then
        fail "HTTP mode: /healthz missing server name"
    fi
    pass "HTTP mode: /healthz 200 ok with server name"

    # No bearer token should be rejected on protected endpoints.
    local status
    status=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/mcp || echo 000)
    if [[ "$status" != "401" && "$status" != "403" ]]; then
        fail "HTTP mode: /mcp without bearer returned $status, expected 401/403"
    fi
    pass "HTTP mode: /mcp without bearer rejected with $status"
}

# ---------------------------------------------------------------------------
# 4. HTTP loopback transport
# ---------------------------------------------------------------------------

test_http_loopback() {
    info "HTTP loopback transport"
    local container body
    container=$(docker run -d --rm \
        -e MCP_TRANSPORT=http-loopback \
        --name pw-loopback \
        "$IMAGE")
    trap 'docker rm -f pw-loopback >/dev/null 2>&1 || true' RETURN

    # Wait for the listener and probe from inside the container, since
    # http-loopback binds 127.0.0.1 inside the network namespace.
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        if body=$(docker exec "$container" python3 -c \
            "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2).read().decode())" \
            2>/dev/null); then
            break
        fi
        sleep 0.5
    done
    if [[ -z "${body:-}" ]]; then
        docker logs "$container" >&2 || true
        fail "HTTP loopback: /healthz never became reachable inside the container"
    fi
    if ! printf '%s' "$body" | grep -q '"status":"ok"'; then
        fail "HTTP loopback: /healthz returned '$body'"
    fi
    pass "HTTP loopback: /healthz 200 ok from inside container"
}

# ---------------------------------------------------------------------------
# 5. OCI label round-trip
# ---------------------------------------------------------------------------

test_oci_label() {
    info "OCI label io.docker.server.metadata"
    local label
    label=$(docker inspect --format '{{index .Config.Labels "io.docker.server.metadata"}}' "$IMAGE")
    if [[ -z "$label" || "$label" = "<no value>" ]]; then
        fail "OCI label io.docker.server.metadata is missing"
    fi
    local tools_count
    tools_count=$(printf '%s' "$label" | python3 -c \
        "import sys, json; data = json.loads(sys.stdin.read()); print(len(data['tools']))")
    if [[ "$tools_count" != "9" ]]; then
        fail "OCI label: expected 9 tools, found $tools_count"
    fi
    pass "OCI label parses as JSON with 9 tools"
}

# ---------------------------------------------------------------------------
# 6. Non-root user
# ---------------------------------------------------------------------------

test_non_root_user() {
    info "Container runs as non-root user"
    local user
    user=$(docker inspect --format '{{.Config.User}}' "$IMAGE")
    if [[ -z "$user" || "$user" = "root" || "$user" = "0" ]]; then
        fail "container is configured to run as '$user'"
    fi
    pass "container user is '$user'"
}

# ---------------------------------------------------------------------------
# 7. Embedded /mcp/mcp.yaml
# ---------------------------------------------------------------------------

test_embedded_manifest() {
    info "Embedded /mcp/mcp.yaml"
    local manifest
    manifest=$(docker run --rm --entrypoint cat "$IMAGE" /mcp/mcp.yaml)
    if ! printf '%s' "$manifest" | python3 -c \
        "import sys, yaml; data = yaml.safe_load(sys.stdin); assert data['name'] == 'percival-weather-mcp'" \
        2>/dev/null; then
        fail "/mcp/mcp.yaml is not valid YAML or has wrong name"
    fi
    pass "/mcp/mcp.yaml is valid YAML with name 'percival-weather-mcp'"
}

main() {
    require_image
    test_non_root_user
    test_oci_label
    test_embedded_manifest
    test_stdio_gateway
    test_http_transport
    test_http_loopback
    printf '\n\033[32mAll smoke tests passed.\033[0m\n'
}

main "$@"