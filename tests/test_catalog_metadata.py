"""Tests for the catalog metadata and the product's own VEX document.

Two things are pinned here:

* the catalog entry must bind the image to a real source revision — never to
  the package version, which is what the entry used to carry;
* the OpenVEX document must stay a valid disposition: every CVE the F3 gate
  triaged has a statement, every statement is bound to a digest, and the
  labels are the ones the OpenVEX schema defines.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_YAML = REPO_ROOT / "docs/mcp/percival-weather-mcp/server.yaml"
OPENVEX = REPO_ROOT / "docs/security/openvex.json"
F3_NOTE = REPO_ROOT / "docs/issues/2026-10-10-f3-status.md"

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
OPENVEX_STATUSES = {"not_affected", "affected", "fixed", "under_investigation"}
OPENVEX_JUSTIFICATIONS = {
    "component_not_present",
    "vulnerable_code_not_present",
    "vulnerable_code_not_in_execute_path",
    "vulnerable_code_cannot_be_controlled_by_adversary",
    "inline_mitigations_already_exist",
}


@pytest.fixture(scope="module")
def server_yaml() -> dict:
    return yaml.safe_load(SERVER_YAML.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def openvex() -> dict:
    return json.loads(OPENVEX.read_text(encoding="utf-8"))


def test_source_commit_is_a_real_revision(server_yaml: dict) -> None:
    """A-004: the catalog entry must cite a commit, not the package version."""
    commit = server_yaml["source"]["commit"]
    assert SHA_RE.match(commit), f"source.commit must be a full commit SHA, got {commit!r}"
    assert commit != "0.9.0"


def test_server_yaml_keeps_its_identity(server_yaml: dict) -> None:
    assert server_yaml["name"] == "percival-weather-mcp"
    assert server_yaml["image"] == "mcp/percival-weather-mcp"
    assert server_yaml["type"] == "server"


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
    note = F3_NOTE.read_text(encoding="utf-8")
    triaged = set(re.findall(r"CVE-\d{4}-\d+", note))
    # The note abbreviates a group of advisories as "CVE-2026-78408/09/10".
    triaged |= {f"CVE-2026-784{number}" for number in ("08", "09", "10")}
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
