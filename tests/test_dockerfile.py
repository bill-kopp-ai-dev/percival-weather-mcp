"""Static checks for the Dockerfile.

These tests do not require a running Docker daemon — they read the
``Dockerfile`` as text and assert on its structure. The point is to
catch regressions in the image contract (entrypoint, default CMD,
non-root user, etc.) before they reach CI.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / "Dockerfile"
ENTRYPOINT = REPO_ROOT / "docker-entrypoint.sh"
MCP_MANIFEST = REPO_ROOT / "mcp.yaml"


@pytest.fixture(scope="module")
def dockerfile_text() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def entrypoint_text() -> str:
    return ENTRYPOINT.read_text(encoding="utf-8")


def test_dockerfile_exists():
    assert DOCKERFILE.is_file(), "Dockerfile is missing"


def test_dockerfile_uses_syntax_pragmas(dockerfile_text: str):
    assert re.search(r"^#\s*syntax=docker/dockerfile:", dockerfile_text, re.MULTILINE)


def test_dockerfile_uses_supported_python_image(dockerfile_text: str):
    matches = re.findall(r"^FROM python:(\d+\.\d+)-slim", dockerfile_text, re.MULTILINE)
    assert matches, "Dockerfile must build on python:<version>-slim"
    assert all(float(v) >= 3.10 for v in matches), (
        "python:3.10 or newer is required by pyproject.toml"
    )


def test_dockerfile_has_multistage_build(dockerfile_text: str):
    """The image must keep the runtime layer slim by separating build deps."""
    from_lines = [line for line in dockerfile_text.splitlines() if line.startswith("FROM ")]
    assert len(from_lines) >= 2, "Dockerfile must have a builder + runtime stage"


def test_dockerfile_runs_as_non_root(dockerfile_text: str):
    """The runtime stage must drop privileges."""
    runtime_section = dockerfile_text.split("FROM ", 2)[-1]
    assert "USER app" in runtime_section, "runtime stage must finish with USER app"


def test_dockerfile_uses_entrypoint(dockerfile_text: str):
    """An ENTRYPOINT is required so the gateway can pass transport flags."""
    assert re.search(r"^ENTRYPOINT\s+\[", dockerfile_text, re.MULTILINE), (
        "Dockerfile must declare an exec-form ENTRYPOINT"
    )


def test_dockerfile_entrypoint_is_executable_in_image(dockerfile_text: str):
    """The entrypoint file must be chmod +x inside the image."""
    assert "chmod 0755" in dockerfile_text or "chmod +x" in dockerfile_text


def test_dockerfile_default_cmd_is_stdio(dockerfile_text: str):
    """Default CMD must be ``stdio`` so ``docker run -i …`` Just Works."""
    match = re.search(
        r"^CMD\s+\[\"([^\"]+)\"(?:\s*,\s*\"([^\"]+)\")?\]", dockerfile_text, re.MULTILINE
    )
    assert match is not None, "Dockerfile must declare an exec-form CMD"
    parts = [match.group(1)]
    if match.group(2):
        parts.append(match.group(2))
    assert parts == ["stdio"], "default CMD must be ['stdio'] so the gateway spawn is drop-in"


def test_dockerfile_exposes_http_port(dockerfile_text: str):
    """The image must still document the HTTP listen port for operators."""
    assert "EXPOSE 8080" in dockerfile_text


def test_dockerfile_copies_entrypoint(dockerfile_text: str):
    """The entrypoint script must be copied into the image."""
    assert "docker-entrypoint.sh" in dockerfile_text


def test_dockerfile_copies_mcp_manifest(dockerfile_text: str):
    """The toolkit manifest must be copied into the image."""
    assert "mcp.yaml" in dockerfile_text


def test_entrypoint_script_exists():
    assert ENTRYPOINT.is_file()


def test_entrypoint_script_is_executable():
    mode = ENTRYPOINT.stat().st_mode
    assert mode & 0o111, "docker-entrypoint.sh must be executable"


def test_entrypoint_script_uses_posix_sh(entrypoint_text: str):
    """Must not depend on bash — Alpine / slim base images only ship POSIX sh."""
    assert entrypoint_text.startswith("#!/bin/sh\n") or entrypoint_text.startswith("#!/bin/sh ")


def test_entrypoint_script_dispatches_on_mcp_transport(entrypoint_text: str):
    """Default must be stdio; ``MCP_TRANSPORT=http`` must switch to HTTP."""
    assert "MCP_TRANSPORT" in entrypoint_text
    assert "--mode stdio" in entrypoint_text
    assert "--mode streamable-http" in entrypoint_text


def test_entrypoint_script_keeps_127_loopback_for_local_http(entrypoint_text: str):
    """``http-loopback`` mode must bind to 127.0.0.1 (no remote exposure)."""
    assert "127.0.0.1" in entrypoint_text


def test_mcp_manifest_exists():
    assert MCP_MANIFEST.is_file()
