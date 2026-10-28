#!/usr/bin/env python3
"""Latencia de encerramento (EOF no stdin) e tratamento de SIGTERM.

Duas medicoes complementares no container do `percival-weather-mcp`:

1. `eof`: fecha o stdin imediatamente e mede quanto tempo o container leva
   para encerrar (codigo de saida e atraso).
2. `sigterm`: mantem o container vivo, envia SIGTERM e mede codigo de saida,
   tempo ate a morte e presenca de log de shutdown.

Uso:
  wx_lifecycle.py --image IMAGEM [--runs 8] [--mode eof|sigterm|both]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone


def _parse_log_ts(line: str) -> float | None:
    """Extrai o timestamp UTC (prefixo 'YYYY-MM-DD HH:MM:SS,mmm') de uma linha de log."""
    try:
        parts = line.split(" ")
        date_part, time_part = parts[0], parts[1]
        hour, minute, second = time_part.split(":")
        millis = int(second.split(",")[1])
        base = datetime.strptime(
            f"{date_part} {hour}:{minute}:{second.split(',')[0]}", "%Y-%m-%d %H:%M:%S"
        )
        return base.replace(tzinfo=timezone.utc).timestamp() + millis / 1000.0
    except Exception:
        return None


def run_eof(image: str, timeout: float) -> dict:
    command = [
        "docker",
        "run",
        "--rm",
        "-i",
        "--init",
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        "/tmp:size=64m,mode=1777,noexec,nosuid,nodev",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--user",
        "999:999",
        image,
    ]
    started = time.monotonic()
    process = subprocess.Popen(
        command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    try:
        _, err = process.communicate(timeout=timeout)
        exited_at = datetime.now(timezone.utc).timestamp()
        lines = err.strip().splitlines()
        # A ultima linha de log com timestamp marca o inicio do loop stdio;
        # o intervalo entre ela e a saida e o atraso de encerramento.
        stamps = [ts for ts in (_parse_log_ts(line) for line in lines) if ts is not None]
        linger = round(exited_at - max(stamps), 2) if stamps else None
        return {
            "exit_code": process.returncode,
            "seconds_to_exit": round(time.monotonic() - started, 2),
            "linger_after_last_log_s": linger,
            "stderr_tail": err.strip().splitlines()[-4:],
        }
    except subprocess.TimeoutExpired:
        process.kill()
        return {"exit_code": None, "seconds_to_exit": None, "timeout": timeout}


def run_sigterm(image: str, timeout: float) -> dict:
    """SIGTERM enviado ao container (nao ao `docker run`), com codigo lido do daemon."""
    name = "iac-wx-sigterm"
    subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True)
    command = [
        "docker",
        "run",
        "-d",
        "-i",
        "--init",
        "--name",
        name,
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        "/tmp:size=64m,mode=1777,noexec,nosuid,nodev",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--user",
        "999:999",
        image,
    ]
    subprocess.run(command, check=True, capture_output=True)
    process = subprocess.Popen(
        ["docker", "logs", "-f", name], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    time.sleep(6)
    started = time.monotonic()
    subprocess.run(["docker", "kill", "--signal=SIGTERM", name], check=False, capture_output=True)
    exit_code = None
    for _ in range(int(timeout)):
        inspected = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.ExitCode}}|{{.State.Status}}", name],
            check=False,
            capture_output=True,
            text=True,
        ).stdout.strip()
        code, _, status = inspected.partition("|")
        if status not in {"running", "restarting"}:
            exit_code = code
            break
        time.sleep(1)
    # ``docker logs`` writes the container stdout to our stdout and the
    # container stderr to our stderr; the server logs to stderr, so both must
    # be captured to observe the shutdown line.
    logs = subprocess.run(
        ["docker", "logs", name],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    ).stdout
    subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True)
    try:
        process.kill()
        process.wait(timeout=5)
    except Exception:
        pass
    lines = logs.strip().splitlines()
    shutdown_logs = [
        line for line in lines if "shutdown" in line.lower() or "shutting" in line.lower()
    ]
    return {
        "exit_code": exit_code,
        "seconds_to_exit": round(time.monotonic() - started, 2),
        "shutdown_log_lines": shutdown_logs,
        "stderr_tail": lines[-6:],
    }


def run_sigint(image: str, timeout: float) -> dict:
    """SIGINT enviado ao container: o processo deve encerrar, nao ficar vivo."""
    name = "iac-wx-sigint"
    subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True)
    command = [
        "docker",
        "run",
        "-d",
        "-i",
        "--init",
        "--name",
        name,
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        "/tmp:size=64m,mode=1777,noexec,nosuid,nodev",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--user",
        "999:999",
        image,
    ]
    subprocess.run(command, check=True, capture_output=True)
    time.sleep(6)
    started = time.monotonic()
    subprocess.run(["docker", "kill", "--signal=SIGINT", name], check=False, capture_output=True)
    exit_code = None
    status = "running"
    for _ in range(int(timeout)):
        inspected = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.ExitCode}}|{{.State.Status}}", name],
            check=False,
            capture_output=True,
            text=True,
        ).stdout.strip()
        code, _, status = inspected.partition("|")
        if status not in {"running", "restarting"}:
            exit_code = code
            break
        time.sleep(0.5)
    logs = subprocess.run(
        ["docker", "logs", name],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    ).stdout
    subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True)
    shutdown_logs = [line for line in logs.strip().splitlines() if "shutting down" in line.lower()]
    return {
        "exit_code": exit_code,
        "status": status,
        "seconds_to_exit": round(time.monotonic() - started, 2),
        "shutdown_log_lines": shutdown_logs,
    }


def run_docker_stop(image: str, timeout: float) -> dict:
    """Ciclo de vida real do daemon: `docker stop` (10 s por padrao) -> codigo de saida."""
    name = "iac-wx-stop"
    subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True)
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "-i",
            "--init",
            "--name",
            name,
            "--network",
            "none",
            "--read-only",
            "--tmpfs",
            "/tmp:size=64m,mode=1777,noexec,nosuid,nodev",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--user",
            "999:999",
            image,
        ],
        check=True,
        capture_output=True,
    )
    time.sleep(6)
    started = time.monotonic()
    subprocess.run(["docker", "stop", name], check=False, capture_output=True)
    elapsed = round(time.monotonic() - started, 2)
    inspected = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.ExitCode}}|{{.State.OOMKilled}}", name],
        check=False,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True)
    code, _, oom = inspected.partition("|")
    return {
        "exit_code": code,
        "oom_killed": oom,
        "seconds_to_stop": elapsed,
        "docker_stop_default_timeout_s": 10,
        "note": "137 = SIGKILL apos escalonamento do timeout padrao do `docker stop`",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--runs", type=int, default=8)
    parser.add_argument(
        "--mode", choices=["eof", "sigterm", "sigint", "stop", "both", "all"], default="both"
    )
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    report: dict = {"image": args.image}
    if args.mode in {"eof", "both"}:
        eof_runs = [run_eof(args.image, args.timeout) for _ in range(args.runs)]
        latencies = [r["seconds_to_exit"] for r in eof_runs if r.get("seconds_to_exit") is not None]
        report["eof"] = {
            "runs": eof_runs,
            "exit_codes": sorted(
                {r.get("exit_code") for r in eof_runs}, key=lambda v: (v is None, v)
            ),
            "latency_min_s": min(latencies) if latencies else None,
            "latency_max_s": max(latencies) if latencies else None,
            "latency_mean_s": round(sum(latencies) / len(latencies), 2) if latencies else None,
        }
    if args.mode in {"sigterm", "both", "all"}:
        report["sigterm"] = run_sigterm(args.image, args.timeout)
    if args.mode in {"sigint", "both", "all"}:
        report["sigint"] = run_sigint(args.image, args.timeout)
    if args.mode in {"stop", "both", "all"}:
        report["docker_stop"] = run_docker_stop(args.image, args.timeout)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
