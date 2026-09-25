"""Behavioural tests for ``docker-entrypoint.sh``.

The image's gateway-mode contract relies on ``CMD ["stdio"]`` reaching the
FastMCP runner with **no extra positional arguments** so Python's argparse
does not error out with ``unrecognized arguments: stdio``. We also want
operators to be able to flip the transport from the command line
(``docker run <image> http``) or via ``MCP_TRANSPORT=http``.

These tests shell out to a tiny POSIX ``sh`` driver that ``exec``'s the
real entrypoint with a controlled environment and assert on the captured
argv.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = REPO_ROOT / "docker-entrypoint.sh"


@pytest.fixture(scope="module")
def sh() -> str:
    """Return the POSIX ``sh`` interpreter available on the host."""
    for candidate in ("/bin/sh", "/usr/bin/sh"):
        if Path(candidate).is_file():
            return candidate
    pytest.skip("no POSIX sh interpreter available")


@pytest.fixture(scope="module")
def stub_python(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Write a tiny ``python`` shim that records the argv it was called with.

    The shim writes each argument on its own line to ``$STUB_RECORD`` so the
    tests can assert on the exact command line the entrypoint would forward
    to the real Python interpreter.
    """
    shim_dir = tmp_path_factory.mktemp("entrypoint-shim")
    record = shim_dir / "argv.txt"
    record.write_text("", encoding="utf-8")
    python_path = shim_dir / "python"
    python_path.write_text(
        '#!/bin/sh\nprintf \'%s\\n\' "$@" >> "$STUB_RECORD"\n',
        encoding="utf-8",
    )
    python_path.chmod(0o755)
    return shim_dir


def _run_entrypoint(
    sh: str,
    python_dir: Path,
    record: Path,
    *,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> list[str]:
    full_env = {
        "PATH": f"{python_dir}:{os.environ.get('PATH', '')}",
        "STUB_RECORD": str(record),
    }
    if env:
        full_env.update(env)
    result = subprocess.run(
        [sh, str(ENTRYPOINT), *(args or [])],
        capture_output=True,
        text=True,
        env=full_env,
        check=True,
    )
    assert result.stdout == "", (
        f"entrypoint should exec the python shim silently; got stdout={result.stdout!r}"
    )
    return [line for line in record.read_text(encoding="utf-8").splitlines() if line]


def test_default_cmd_does_not_pass_stdio_as_positional(
    sh: str, stub_python: Path, tmp_path: Path
) -> None:
    """``CMD ["stdio"]`` must NOT leak ``stdio`` into the python argv.

    Regression: the entrypoint used to unconditionally forward ``"$@"``
    even when the transport was stdio, producing
    ``python -m percival_weather_mcp --mode stdio stdio`` and an argparse
    "unrecognized arguments: stdio" error.
    """
    record = tmp_path / "argv.txt"
    argv = _run_entrypoint(sh, stub_python, record, args=["stdio"])
    assert "--mode" in argv
    assert "stdio" in argv, "stdio is the default mode and must be passed as the value of --mode"
    # The CMD value 'stdio' must NOT also appear as a standalone positional.
    assert argv.count("stdio") == 1, (
        f"--mode stdio is fine, but 'stdio' leaked as a positional too: {argv!r}"
    )
    assert "-m" in argv
    assert "percival_weather_mcp" in argv


def test_mcp_transport_http_passes_remote_flag(sh: str, stub_python: Path, tmp_path: Path) -> None:
    """``MCP_TRANSPORT=http`` must bind 0.0.0.0 with ``--allow-remote-http``."""
    record = tmp_path / "argv.txt"
    argv = _run_entrypoint(
        sh,
        stub_python,
        record,
        env={"MCP_TRANSPORT": "http", "PORT": "9090"},
    )
    assert "streamable-http" in argv
    assert "0.0.0.0" in argv
    assert "9090" in argv
    assert "--allow-remote-http" in argv
    assert "--allow-remote-http=false" not in argv


def test_mcp_transport_http_loopback_uses_localhost(
    sh: str, stub_python: Path, tmp_path: Path
) -> None:
    """``MCP_TRANSPORT=http-loopback`` must bind 127.0.0.1 and refuse remote.

    The entrypoint relies on argparse's default (``False``) for the
    ``--allow-remote-http`` store-true flag; passing ``--allow-remote-http=false``
    explicitly is rejected by argparse, so we simply omit the flag.
    """
    record = tmp_path / "argv.txt"
    argv = _run_entrypoint(
        sh,
        stub_python,
        record,
        env={"MCP_TRANSPORT": "http-loopback"},
    )
    assert "127.0.0.1" in argv
    assert "0.0.0.0" not in argv
    assert "--allow-remote-http" not in argv


def test_positional_http_overrides_default_transport(
    sh: str, stub_python: Path, tmp_path: Path
) -> None:
    """A positional ``http`` arg must flip to HTTP without ``MCP_TRANSPORT``."""
    record = tmp_path / "argv.txt"
    argv = _run_entrypoint(sh, stub_python, record, args=["http"])
    assert "streamable-http" in argv
    assert "--allow-remote-http" in argv


def test_entrypoint_is_posix_sh():
    """The entrypoint must keep using ``/bin/sh`` (Alpine compat)."""
    first_line = ENTRYPOINT.read_text(encoding="utf-8").splitlines()[0]
    assert first_line in {"#!/bin/sh", "#!/bin/sh "}


def test_entrypoint_handles_unset_path():
    """The script must not assume a particular PATH layout at runtime."""
    text = ENTRYPOINT.read_text(encoding="utf-8")
    # ``PATH`` should never be hard-coded; only ``$PATH`` references are OK.
    assert "PATH=/" not in text
