"""Tests for the distribution metadata and the product's own VEX document.

Two things are pinned here:

* the distribution metadata must describe the artifact that actually ships —
  the OCI package behind ``server.json`` and the PBLabs extension behind
  ``pblabs.app.yaml`` — with a version that matches the product, and without
  re-introducing the abandoned Docker MCP Catalog path (``R-06``);
* the OpenVEX document must stay a valid disposition: every CVE the F3 gate
  triaged has a statement, every statement is bound to a digest, and the
  labels are the ones the OpenVEX schema defines.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import tomllib
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
MCP_DIR = REPO_ROOT / "docs" / "mcp" / "percival-weather-mcp"
SERVER_JSON = MCP_DIR / "server.json"
PBLABS_APP_YAML = MCP_DIR / "pblabs.app.yaml"
OPENVEX = REPO_ROOT / "docs/security/openvex.json"

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
OPENVEX_STATUSES = {"not_affected", "affected", "fixed", "under_investigation"}
OPENVEX_JUSTIFICATIONS = {
    "component_not_present",
    "vulnerable_code_not_present",
    "vulnerable_code_not_in_execute_path",
    "vulnerable_code_cannot_be_controlled_by_adversary",
    "inline_mitigations_already_exist",
}


def _product_version() -> str:
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


@pytest.fixture(scope="module")
def server_json() -> dict:
    return json.loads(SERVER_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def pblabs_app() -> dict:
    return yaml.safe_load(PBLABS_APP_YAML.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def openvex() -> dict:
    return json.loads(OPENVEX.read_text(encoding="utf-8"))


def test_server_json_declares_the_oci_package(server_json: dict) -> None:
    """A-004: the metadata must name the package that is actually shipped."""
    assert server_json["$schema"].startswith("https://static.modelcontextprotocol.io/schemas/")
    assert server_json["name"].startswith("io.github.")
    assert server_json["version"] == _product_version()
    assert server_json["repository"]["url"].startswith("https://")

    packages = server_json["packages"]
    assert packages, "server.json must declare at least one package"
    package = packages[0]
    assert package["registryType"] == "oci"
    assert package["version"] == _product_version()
    assert package["transport"]["type"] == "stdio"
    assert package["runtimeHint"] == "docker"
    assert SEMVER_RE.match(package["version"]), package["version"]


def test_server_json_version_is_not_used_as_a_revision(server_json: dict) -> None:
    """A-004: a bare version must never stand in for a source revision."""
    version = server_json["version"]
    assert not SHA_RE.match(version), "the version field must not hold a commit SHA"
    assert version != "0.9.0", "the metadata must track the current product version"


def test_pblabs_extension_matches_the_server_metadata(server_json: dict, pblabs_app: dict) -> None:
    assert pblabs_app["schema_version"] == "0.2"
    assert pblabs_app["mcp_name"] == server_json["name"]
    assert pblabs_app["version"] == server_json["version"]
    assert pblabs_app["runtime"]["container"] is True
    assert pblabs_app["runtime"]["transport"] == "stdio"
    assert pblabs_app["mounts"] == []
    assert pblabs_app["review"]["status"] == "manifest-approved"


def test_docker_mcp_catalog_is_not_a_dependency() -> None:
    """R-06: the Docker MCP Catalog is not part of the distribution path."""
    for path in sorted(MCP_DIR.rglob("*.y*ml")):
        content = path.read_text(encoding="utf-8")
        assert "mcp/percival-weather-mcp" not in content, (
            f"{path.name} still points at the abandoned Docker MCP Catalog namespace"
        )


def test_openvex_has_the_required_envelope(openvex: dict) -> None:
    assert openvex["@context"] == "https://openvex.dev/ns/v0.2.0"
    assert openvex["@id"].endswith("docs/security/openvex.json")
    for field in ("author", "timestamp", "version", "statements"):
        assert field in openvex, f"missing {field}"
    assert openvex["statements"], "the document must carry at least one statement"


def test_every_statement_is_well_formed(openvex: dict) -> None:
    for statement in openvex["statements"]:
        assert statement["vulnerability"]["name"].startswith("CVE-")
        assert statement["status"] in OPENVEX_STATUSES
        if "justification" in statement:
            assert statement["justification"] in OPENVEX_JUSTIFICATIONS
        for field in ("impact_statement", "action_statement"):
            assert statement.get(field), f"{statement['vulnerability']['name']} has no {field}"
        products = statement.get("products") or []
        assert products, f"{statement['vulnerability']['name']} is not bound to a product"
        for product in products:
            assert "@sha256:" in product["@id"], product["@id"]


def test_every_cve_of_the_f3_gate_has_a_statement(openvex: dict) -> None:
    """The document must cover the CVEs the F3 gate recorded, and nothing else."""
    # Historical disposition only: frozen triage at 9746453, formerly in the
    # local F3 tracker (now under internal/, not published). The live tracker
    # was centralized; its current findings must not redefine this older
    # digest's VEX scope.
    triaged = {
        "CVE-2026-76642",
        "CVE-2026-78408",
        "CVE-2026-78409",
        "CVE-2026-78410",
        "CVE-2026-54369",
        "CVE-2025-69720",
        "CVE-2026-16742",
        "CVE-2026-9538",
    }
    documented = {s["vulnerability"]["name"] for s in openvex["statements"]}
    assert triaged, "the F3 note no longer names any CVE"
    assert documented == triaged, (
        f"missing: {sorted(triaged - documented)}; unexpected: {sorted(documented - triaged)}"
    )


def test_the_products_of_the_document_share_one_digest(openvex: dict) -> None:
    """A disposition that spans digests would apply to images that were never scanned."""
    digests = {
        product["@id"].split("@sha256:")[1]
        for statement in openvex["statements"]
        for product in statement.get("products") or []
    }
    assert len(digests) == 1, f"the document covers more than one digest: {sorted(digests)}"
