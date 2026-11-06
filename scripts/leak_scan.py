"""Fail the build when the published tree carries references that must not leave it.

The repository is public. Some material belongs to the owner's internal
process — local paths, sibling repositories that are not published, the agent
runtime directory — and must never reach the published tree. The working
checkout keeps that material under ``internal/``, which is gitignored, so a
scan of the *tracked* files is enough to catch a regression.

This script enumerates the tracked files with ``git ls-files`` and applies
every rule below. A violation makes the script exit non-zero, which is what
the CI step relies on.

The two files that define and test the rules must spell the patterns out, so
they are exempt from every rule by path. The exemption is explicit and
minimal; ``tests/test_leak_scan.py`` asserts that no other path is exempt.

Usage::

    python scripts/leak_scan.py            # report and exit 1 on any finding
    python scripts/leak_scan.py --quiet    # exit status only
    python scripts/leak_scan.py --root DIR # scan another checkout
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# The files that spell out the forbidden patterns. They are exempt from every
# rule: a scanner that flagged its own rule table would fail every build.
DEFINITION_FILES = frozenset({"scripts/leak_scan.py", "tests/test_leak_scan.py"})


@dataclass(frozen=True)
class Rule:
    """One forbidden pattern and the files that are allowed to contain it."""

    name: str
    pattern: re.Pattern[str]
    rationale: str
    exempt: frozenset[str] = frozenset()


RULES: tuple[Rule, ...] = (
    Rule(
        name="absolute-home-path",
        pattern=re.compile(r"/home/[A-Za-z0-9._-]+/"),
        rationale="an absolute path into a developer's home directory",
    ),
    Rule(
        name="internal-runtime-path",
        pattern=re.compile(r"\.positronic/"),
        rationale="a path inside the internal agent runtime",
        exempt=frozenset({".gitignore", ".dockerignore"}),
    ),
    Rule(
        name="unpublished-repository",
        pattern=re.compile(r"alternative-positronic|positronic-bean-IaC|pblabs-mcp-index"),
        rationale="a sibling repository that is not published",
    ),
    Rule(
        name="owner-email-outside-mailmap",
        pattern=re.compile(r"bill\.kopp\.dev@gmail\.com"),
        rationale="the owner's personal address, which belongs in the attribution map only",
        exempt=frozenset({".mailmap"}),
    ),
)


@dataclass(frozen=True)
class Finding:
    """A rule violation at one location of one file."""

    rule: str
    path: str
    line: int
    column: int
    match: str
    rationale: str


def tracked_files(root: Path = REPO_ROOT) -> list[str]:
    """Return the paths git tracks, so ignored files are excluded by construction."""
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        capture_output=True,
        check=True,
    )
    return [path for path in completed.stdout.decode("utf-8").split("\0") if path]


def is_binary(raw: bytes) -> bool:
    """Report whether the payload looks like a binary file."""
    return b"\0" in raw[:8192]


def scan_text(path: str, text: str, rules: tuple[Rule, ...]) -> list[Finding]:
    """Apply every rule to one text file and return the violations."""
    if path in DEFINITION_FILES:
        return []
    findings: list[Finding] = []
    for rule in rules:
        if path in rule.exempt:
            continue
        for match in rule.pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            line_start = text.rfind("\n", 0, match.start()) + 1
            findings.append(
                Finding(
                    rule=rule.name,
                    path=path,
                    line=line,
                    column=match.start() - line_start + 1,
                    match=match.group(0),
                    rationale=rule.rationale,
                )
            )
    return findings


def scan(root: Path = REPO_ROOT, rules: tuple[Rule, ...] = RULES) -> list[Finding]:
    """Scan every tracked text file and return the violations, sorted."""
    findings: list[Finding] = []
    for relative in tracked_files(root):
        path = root / relative
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if is_binary(raw):
            continue
        findings.extend(scan_text(relative, raw.decode("utf-8", errors="replace"), rules))
    return sorted(findings, key=lambda item: (item.rule, item.path, item.line, item.column))


def report(findings: list[Finding]) -> str:
    """Render the violations as a human-readable report."""
    if not findings:
        return "leak scan: no violations in the tracked tree"
    lines = [f"leak scan: {len(findings)} violation(s) in the tracked tree"]
    for finding in findings:
        lines.append(
            f"  {finding.path}:{finding.line}:{finding.column}: "
            f"[{finding.rule}] {finding.match!r} — {finding.rationale}"
        )
    lines.append(
        "  Keep internal records under 'internal/' (gitignored) and refer to them in prose, "
        "not by path."
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Run the scan and return the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true", help="print nothing; report by exit code")
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="checkout to scan (default: the repository this script lives in)",
    )
    args = parser.parse_args(argv)

    findings = scan(args.root)
    if not args.quiet:
        print(report(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
