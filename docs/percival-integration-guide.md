# Percival Weather MCP integration

## Runtime profile

- Use the container in **stdio** mode for the Percival MCP manager. Attach stdin
  and stdout; stdout is reserved for JSON-RPC. Do not publish a port or add an
  HTTP health check to this profile.
- The service is stateless and requires no host files or credentials:
  `mounts: []`, no persistent data, and no required secrets. Open-Meteo calls
  require outbound network access.
- Run the container with one init layer supplied by its runtime/manager. The
  manager owns restart policy and lifecycle. The observed product behavior is
  EOF exit 0, SIGTERM exit 143, and SIGINT termination; see the Stage-2 plan for
  dated candidate evidence.

## MCP capabilities and consumer behavior

The server exposes 9 tools, 3 prompts, 3 resources, and 1 resource template.
The current Percival `MCPProvider` integration consumes `tools/list`; it does
not currently surface MCP prompts/resources to the agent. The server still
registers those capabilities and they remain available to clients that request
them. In particular, `weather://timezones` is readable by MCP clients that
support resources. Do not describe these server capabilities as absent merely
because this consumer does not expose them.

## Optional HTTP profile

HTTP is a separate opt-in mode, not the Percival stdio profile. Bind it to
loopback unless a deployment has an explicit network and authentication
design. `/mcp` requires the configured bearer token; `/metrics` also requires
it when configured; `/healthz` and `/health` remain unauthenticated liveness
probes. With no token configured, authentication is not enforced. Never put a
real token in this document or a committed profile.

## Distribution status

The Docker MCP Catalog manifest in `docs/mcp/percival-weather-mcp/server.yaml`
belongs to the superseded Docker Catalog path. The selected PBLabs index
contract is staged as draft metadata under
`docs/mcp/percival-weather-mcp/`. A draft or schema-valid manifest is not a
published image, verified namespace claim, digest, signed VEX, or release
approval. Follow the Stage-2 plan's gates before any publication or deployment.

## Verification boundaries

Local tests and simulated Open-Meteo fixtures establish product behavior but
do not prove availability or correctness of the live provider. A controlled
provider validation is recorded separately in the Stage-2 plan. CI and image
scans apply only to their recorded source revision and image identity.
