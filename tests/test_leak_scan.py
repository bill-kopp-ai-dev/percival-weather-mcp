"""The published tree must not carry references that belong to internal work.

The repository is public. Local paths, unpublished sibling repositories, the
agent runtime directory and the owner's personal address are internal: they
belong under ``internal/`` (gitignored) or in the attribution map, never in a
document that ships with the product.

``scripts/leak_scan.py`` is the CI gate. These tests pin the rules it applies
and prove the tracked tree is clean, so a regression fails the build instead of
being discovered after publication.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "leak_scan.py"


def _load_module():
    """Import ``leak_scan.py`` from the scripts directory, which is not a package."""
    spec = importlib.util.spec_from_file_location("leak_scan", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


leak_scan = _load_module()


def _rules_for(*names: str):
    return tuple(rule for rule in leak_scan.RULES if rule.name in names)


def test_the_tracked_tree_is_clean() -> None:
    """No tracked file may carry a forbidden reference."""
    assert leak_scan.scan(REPO_ROOT) == []


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ("checkout at /home/bill/Projects/percival-weather-mcp", "absolute-home-path"),
        ("see the tracker in pblabs-mcp-index", "unpublished-repository"),
        ("see the sibling alternative-positronic", "unpublished-repository"),
        ("see the sibling positronic-bean-IaC", "unpublished-repository"),
        ("evidence lives in .positronic/journal", "internal-runtime-path"),
        ("mail the owner at bill.kopp.dev@gmail.com", "owner-email-outside-mailmap"),
    ],
)
def test_forbidden_references_are_reported(text: str, rule: str) -> None:
    """Every forbidden pattern must be reported with its location."""
    findings = leak_scan.scan_text("docs/probe.md", text, _rules_for(rule))
    assert len(findings) == 1
    assert findings[0].rule == rule
    assert findings[0].path == "docs/probe.md"
    assert findings[0].line == 1
    assert findings[0].column == text.index(findings[0].match) + 1


def test_the_ignore_rules_may_name_the_internal_runtime() -> None:
    """``.gitignore`` and ``.dockerignore`` exist to exclude that directory."""
    for path in (".gitignore", ".dockerignore"):
        findings = leak_scan.scan_text(path, ".positronic/\n", _rules_for("internal-runtime-path"))
        assert findings == []


def test_the_attribution_map_may_name_the_owner() -> None:
    """``.mailmap`` is where the owner's address belongs."""
    findings = leak_scan.scan_text(
        ".mailmap",
        "Bill Kopp <bill.kopp.dev@gmail.com> <bill@example.com>\n",
        _rules_for("owner-email-outside-mailmap"),
    )
    assert findings == []


def test_only_the_rule_definitions_are_exempt_from_every_rule() -> None:
    """The exemption that covers the rule table itself must stay minimal."""
    assert {"scripts/leak_scan.py", "tests/test_leak_scan.py"} == leak_scan.DEFINITION_FILES
    for path in leak_scan.DEFINITION_FILES:
        assert leak_scan.scan_text(path, "/home/bill/Projects/x\n", leak_scan.RULES) == []


def test_a_file_that_is_not_a_definition_is_not_exempt() -> None:
    """Exemption is by path, not by content: only the two files are exempt."""
    findings = leak_scan.scan_text(
        "scripts/other_tool.py",
        "/home/bill/Projects/x\n",
        leak_scan.RULES,
    )
    assert [finding.rule for finding in findings] == ["absolute-home-path"]


def test_the_scan_covers_only_tracked_files(tmp_path: Path) -> None:
    """An ignored file must not be able to fail the gate."""
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("local.md\n", encoding="utf-8")
    (tmp_path / "local.md").write_text("/home/bill/Projects/x\n", encoding="utf-8")
    (tmp_path / "tracked.md").write_text("nothing to see\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", ".gitignore"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "-f", "tracked.md"], check=True)

    assert leak_scan.scan(tmp_path) == []

    subprocess.run(["git", "-C", str(tmp_path), "add", "-f", "local.md"], check=True)
    findings = leak_scan.scan(tmp_path)
    assert [finding.rule for finding in findings] == ["absolute-home-path"]


def test_the_gate_fails_a_checkout_that_leaks(tmp_path: Path) -> None:
    """The script must exit non-zero when a tracked file violates a rule."""
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    (tmp_path / "leak.md").write_text("pblabs-mcp-index\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "leak.md"], check=True)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "unpublished-repository" in result.stdout


def test_the_gate_passes_a_clean_checkout(tmp_path: Path) -> None:
    """A clean checkout must exit zero and report nothing."""
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    (tmp_path / "README.md").write_text("nothing to see\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "README.md"], check=True)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "no violations" in result.stdout
