"""Validate the OCI ``io.docker.server.metadata`` label embedded in the image.

The Docker MCP Toolkit gateway (``docker/mcp-gateway``) reads this label from
the image's OCI config — *not* any file inside the image. The label payload
must match ``catalog.ImportedServer``:

* ``name``, ``type`` and ``tools[]`` are required. Anything missing causes
  the gateway to reject the image as "not a self-describing image".
* ``command``, ``volumes``, ``user``, ``secrets[]``, ``env[].value`` and
  other runtime-shaping fields are silently dropped (security policy).
* The label is a JSON string, embedded as a single-line ``LABEL`` in the
  Dockerfile.

These tests pin the Dockerfile contents and the schema so a future change
that breaks the gateway contract fails the test suite immediately.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / "Dockerfile"
OCI_LABEL_JSON = REPO_ROOT / "docs/mcp/percival-weather-mcp/oci-label.json"
REGISTRY_TOOLS_JSON = REPO_ROOT / "docs/mcp/percival-weather-mcp/tools.json"

ALLOWED_PRIMITIVE_TYPES = {"string", "number", "integer", "boolean", "array"}
FORBIDDEN_LABEL_FIELDS = {
    "command",
    "volumes",
    "user",
    "extraHosts",
    "allowHosts",
    "disableNetwork",
    "longLived",
    "sseEndpoint",
    "remote",
    "oauth",
    "policy",
    "secrets",
}


@pytest.fixture(scope="module")
def dockerfile_text() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def expected_label() -> dict[str, object]:
    return json.loads(OCI_LABEL_JSON.read_text(encoding="utf-8"))


def _extract_docker_label(dockerfile_text: str, name: str) -> str:
    """Pull the literal value of ``LABEL <name>=<value>`` from the Dockerfile.

    Supports both quoted (``LABEL k="..."``) and unquoted (``LABEL k=...``)
    forms, plus the multi-line continuation syntax
    (``LABEL k1=v1 \\ k2=v2``). Comment lines are skipped so an OCI label
    referenced in a docstring does not collide with the actual instruction.
    """
    lines: list[str] = []
    continuation = False
    capturing = False
    for line in dockerfile_text.splitlines():
        stripped = line.rstrip()
        if stripped.lstrip().startswith("#"):
            continue
        if capturing:
            lines.append(stripped)
            continuation = stripped.endswith("\\")
            if not continuation:
                capturing = False
            continue
        if continuation:
            lines.append(stripped)
            continuation = stripped.endswith("\\")
            continue
        if stripped.startswith("LABEL ") and re.search(rf"\b{re.escape(name)}\s*=", stripped):
            lines.append(stripped)
            continuation = stripped.endswith("\\")
            capturing = continuation
    merged = "\n".join(lines)

    # Quoted form: `name="..."` (handles escaped quotes via \\.)
    match = re.search(
        rf"{re.escape(name)}\s*=\s*\"((?:[^\"\\]|\\.)*)\"",
        merged,
        re.DOTALL,
    )
    if match is not None:
        return match.group(1)
    # Unquoted form: capture until end-of-line or the next ``LABEL`` / ``#``
    # continuation marker. ``{...}`` JSON bodies may contain spaces, so we
    # must not stop at the first whitespace.
    match = re.search(
        rf"{re.escape(name)}\s*=\s*(.+?)(?:\s*\\\s*$|\s*$|\s*#)",
        merged,
        re.MULTILINE,
    )
    if match is None:
        raise AssertionError(f"Dockerfile is missing LABEL {name}=...")
    return match.group(1).strip()


def test_dockerfile_declares_oci_label(dockerfile_text: str):
    assert "io.docker.server.metadata" in dockerfile_text


def test_oci_label_parses_as_json(dockerfile_text: str):
    raw = _extract_docker_label(dockerfile_text, "io.docker.server.metadata")
    parsed = json.loads(raw)
    assert isinstance(parsed, dict)


def test_oci_label_matches_source_of_truth(dockerfile_text: str, expected_label: dict[str, object]):
    raw = _extract_docker_label(dockerfile_text, "io.docker.server.metadata")
    parsed = json.loads(raw)
    assert parsed == expected_label


def test_oci_label_required_fields(expected_label: dict[str, object]):
    """Gateway rejects the image when ``name``, ``type`` or ``tools`` is missing."""
    for field in ("name", "type", "tools"):
        assert field in expected_label, f"label is missing required field '{field}'"


def test_oci_label_type_is_server(expected_label: dict[str, object]):
    assert expected_label["type"] == "server", (
        "gateway only treats 'server' type as stdio MCP; 'remote' or 'poci' need different schemas"
    )


def test_oci_label_has_no_forbidden_fields(expected_label: dict[str, object]):
    """Security policy: runtime-shaping fields must not appear in the label."""
    leaked = FORBIDDEN_LABEL_FIELDS.intersection(expected_label.keys())
    assert not leaked, f"label leaks forbidden fields: {sorted(leaked)}"


def test_oci_label_tools_match_registry_tools_json(expected_label: dict[str, object]):
    """Every advertised tool must also appear in the registry ``tools.json``."""
    label_tool_names = {t["name"] for t in expected_label["tools"]}  # type: ignore[index]
    registry_tools = json.loads(REGISTRY_TOOLS_JSON.read_text(encoding="utf-8"))
    registry_tool_names = {t["name"] for t in registry_tools}
    missing = label_tool_names - registry_tool_names
    extra = registry_tool_names - label_tool_names
    assert not missing, f"label advertises tools not in registry tools.json: {sorted(missing)}"
    assert not extra, f"registry tools.json has tools the label does not: {sorted(extra)}"


def test_oci_label_argument_types_are_registry_friendly(expected_label: dict[str, object]):
    tools = expected_label["tools"]
    assert isinstance(tools, list)
    for tool in tools:
        for arg in tool["arguments"]:  # type: ignore[index]
            assert arg["type"] in ALLOWED_PRIMITIVE_TYPES, (
                f"tool {tool['name']!r} arg {arg['name']!r} has unrecognised type {arg['type']!r}"
            )
            if arg["type"] == "array":
                items = arg.get("items")
                assert isinstance(items, dict) and "type" in items, (
                    f"array arg {tool['name']!r}.{arg['name']!r} must declare items.type"
                )
                assert items["type"] in ALLOWED_PRIMITIVE_TYPES - {"array"}


def test_oci_label_env_entries_carry_only_names(expected_label: dict[str, object]):
    """The gateway drops ``env[].value`` if present; assert we never embed it."""
    env_entries = expected_label.get("env", [])
    assert isinstance(env_entries, list)
    for entry in env_entries:
        assert isinstance(entry, dict)
        assert "name" in entry
        assert "value" not in entry, (
            "image labels must not declare env values (secrets / config handled outside the label)"
        )
