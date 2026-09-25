"""Static validation of the embedded ``mcp.yaml`` manifest.

The Docker MCP Toolkit gateway and various introspection tools read
``mcp.yaml`` to discover the tools, prompts, resources and runtime
configuration of a server image without launching it. These tests pin
the contract so a future change to the manifest cannot silently drop a
tool or break the env-var schema.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
MCP_MANIFEST = REPO_ROOT / "mcp.yaml"
DOCS_TOOLS_JSON = REPO_ROOT / "docs" / "tools.json"


@pytest.fixture(scope="module")
def manifest() -> dict:
    return yaml.safe_load(MCP_MANIFEST.read_text(encoding="utf-8"))


def test_manifest_parses_as_yaml():
    assert MCP_MANIFEST.is_file()


def test_manifest_has_required_top_level_fields(manifest: dict):
    for field in ("name", "title", "version", "transport", "command", "tools"):
        assert field in manifest, f"manifest must declare '{field}'"


def test_manifest_name_matches_package(manifest: dict):
    assert manifest["name"] == "percival-weather-mcp"


def test_manifest_default_transport_is_stdio(manifest: dict):
    assert manifest["transport"] == "stdio"


def test_manifest_command_points_at_entrypoint(manifest: dict):
    cmd = manifest["command"]
    assert isinstance(cmd, list) and cmd, "command must be a non-empty list"
    assert cmd[0].endswith("docker-entrypoint.sh")


def test_manifest_environment_is_well_formed(manifest: dict):
    env = manifest.get("environment", [])
    assert isinstance(env, list)
    for entry in env:
        assert "name" in entry, f"env entry missing 'name': {entry!r}"
        assert isinstance(entry["name"], str)


def test_manifest_documents_mcp_transport_env(manifest: dict):
    names = {entry["name"] for entry in manifest.get("environment", [])}
    assert "MCP_TRANSPORT" in names


def test_manifest_tools_match_server_source_of_truth(manifest: dict):
    """Every advertised tool must appear in the canonical tools.json dump."""
    payload = yaml.safe_load(DOCS_TOOLS_JSON.read_text(encoding="utf-8"))
    server_tools = {tool["name"] for tool in payload["tools"]}
    manifest_tools = {tool["name"] for tool in manifest.get("tools", [])}
    missing = server_tools - manifest_tools
    extra = manifest_tools - server_tools
    assert not missing, f"manifest is missing tools: {sorted(missing)}"
    assert not extra, f"manifest advertises tools not in server: {sorted(extra)}"


def test_manifest_prompts_are_listed(manifest: dict):
    prompts = manifest.get("prompts", [])
    assert "weather_quick_answer" in prompts
    assert "weather_analysis" in prompts
    assert "weather_unit_conversion" in prompts


def test_manifest_resources_are_listed(manifest: dict):
    resources = manifest.get("resources", [])
    for expected in ("weather://codes", "weather://aqi", "weather://timezones"):
        assert expected in resources
