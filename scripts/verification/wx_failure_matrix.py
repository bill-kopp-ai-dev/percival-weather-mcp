#!/usr/bin/env python3
"""Matriz de falhas do `percival-weather-mcp` contra o mock Open-Meteo.

Para cada cenário o script reinicia o container do mock com um `MOCK_MODE`
diferente, zera o log de requisicoes, executa uma sessao MCP real contra a
imagem e registra: `isError`, texto devolvido, numero de requisicoes que o
mock recebeu e o trecho final do stderr do servidor.

Cenarios:
  forecast_500   -> upstream responde 500 (testa retry/backoff e erro)
  forecast_429   -> upstream responde 429 (testa retry por rate limit)
  forecast_empty -> 200 com serie horaria vazia
  geo_notfound   -> geocoding responde sem `results`
  geo_404        -> geocoding responde 404
  hang_timeout   -> upstream nao responde (testa MCP_WEATHER_HTTP_TIMEOUT)

Uso:
  wx_failure_matrix.py --image IMAGEM --mock-image IMAGEM_MOCK
                        --certs-dir DIR --network NOME --mock-ip IP
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time

from wx_mcp_session import McpSession, build_command

MOCK_NAME = "mock-openmeteo"


def restart_mock(
    mock_image: str, mode: str, network: str, ip: str, certs: str, harness: str, logs: str
) -> None:
    subprocess.run(["docker", "rm", "-f", MOCK_NAME], check=False, capture_output=True)
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            MOCK_NAME,
            "--network",
            network,
            "--ip",
            ip,
            "-e",
            f"MOCK_MODE={mode}",
            "-e",
            "MOCK_LOG=/log/mock.log",
            "-v",
            f"{certs}:/certs:ro",
            "-v",
            f"{logs}:/log",
            "-v",
            f"{harness}:/harness:ro",
            mock_image,
            "python",
            "/harness/wx_mock_openmeteo.py",
            "--cert",
            "/certs/server.pem",
            "--key",
            "/certs/server.key",
            "--port",
            "443",
        ],
        check=True,
        capture_output=True,
    )
    time.sleep(2)


def read_log(logs: str) -> list[str]:
    path = f"{logs}/mock.log"
    try:
        with open(path, encoding="utf-8") as handle:
            return [line.strip() for line in handle if line.strip()]
    except FileNotFoundError:
        return []


SCENARIOS = [
    {
        "name": "forecast_500",
        "mode": "500",
        "call": "weather_get_current",
        "args": {"city": "Cidade Teste"},
        "env": ["MCP_WEATHER_HTTP_MAX_RETRIES=2", "MCP_WEATHER_HTTP_BACKOFF_BASE=0.1"],
    },
    {
        "name": "forecast_429",
        "mode": "429",
        "call": "weather_get_current",
        "args": {"city": "Cidade Teste"},
        "env": ["MCP_WEATHER_HTTP_MAX_RETRIES=2", "MCP_WEATHER_HTTP_BACKOFF_BASE=0.1"],
    },
    {
        "name": "forecast_empty",
        "mode": "empty",
        "call": "weather_get_current",
        "args": {"city": "Cidade Teste"},
        "env": [],
    },
    {
        "name": "geo_notfound",
        "mode": "ok",
        "call": "weather_get_current",
        "args": {"city": "Cidade NotFound"},
        "env": [],
    },
    {
        "name": "geo_404",
        "mode": "ok",
        "call": "weather_get_current",
        "args": {"city": "Cidade Offline"},
        "env": [],
    },
    {
        "name": "hang_timeout",
        "mode": "hang",
        "call": "weather_get_current",
        "args": {"city": "Cidade Teste"},
        "env": ["MCP_WEATHER_HTTP_TIMEOUT=2", "MCP_WEATHER_HTTP_MAX_RETRIES=0"],
    },
    {
        "name": "air_quality_500",
        "mode": "500",
        "call": "weather_get_air_quality",
        "args": {"city": "Cidade Teste"},
        "env": ["MCP_WEATHER_HTTP_MAX_RETRIES=0"],
    },
]


def run_scenario(args: argparse.Namespace, scenario: dict) -> dict:
    restart_mock(
        args.mock_image,
        scenario["mode"],
        args.network,
        args.mock_ip,
        args.certs_dir,
        args.harness_dir,
        args.logs_dir,
    )
    log_before = len(read_log(args.logs_dir))

    command = build_command(
        argparse.Namespace(
            image=args.image,
            network=args.network,
            user=args.user,
            certs_dir=args.certs_dir,
            add_host=args.add_host,
            env=list(scenario["env"]),
        )
    )
    session = McpSession(command, args.timeout)
    result: dict = {"scenario": scenario["name"], "mock_mode": scenario["mode"]}
    try:
        init = session.request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "iac-diag", "version": "0.1.0"},
            },
            1,
        )
        if not init or "result" not in init:
            raise RuntimeError(f"initialize falhou: {init}")
        session.notify("notifications/initialized", {})
        payload = session.request(
            "tools/call",
            {"name": scenario["call"], "arguments": scenario["args"]},
            101,
        )
        payload = payload or {}
        tool_result = payload.get("result", {})
        content = tool_result.get("content") or []
        text = content[0].get("text", "") if content and isinstance(content[0], dict) else ""
        result["is_error"] = tool_result.get("isError")
        result["text_head"] = text[:400]
        result["rpc_error"] = payload.get("error")
        result["exit_code"] = session.close_stdin()
        stderr = session.stderr_text().strip().splitlines()
        result["stderr_tail"] = stderr[-6:]
    except Exception as exc:
        result["failure"] = f"{type(exc).__name__}: {exc}"
        if session.process.poll() is None:
            session.process.kill()
            session.process.wait()
        result["stderr_tail"] = session.stderr_text().strip().splitlines()[-6:]
    finally:
        session.selector.close()
    log = read_log(args.logs_dir)
    result["upstream_requests"] = len(log) - log_before
    result["upstream_paths"] = [
        line.split(" ")[1].split("?")[0] for line in log[log_before:] if " " in line
    ]
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--mock-image", default="python:3.12-slim")
    parser.add_argument("--network", required=True)
    parser.add_argument("--mock-ip", required=True)
    parser.add_argument("--certs-dir", required=True)
    parser.add_argument("--logs-dir", required=True)
    parser.add_argument("--harness-dir", required=True)
    parser.add_argument("--user", default="999:999")
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()
    args.add_host = [
        f"api.open-meteo.com:{args.mock_ip}",
        f"geocoding-api.open-meteo.com:{args.mock_ip}",
        f"air-quality-api.open-meteo.com:{args.mock_ip}",
    ]

    report = {"scenarios": []}
    for scenario in SCENARIOS:
        report["scenarios"].append(run_scenario(args, scenario))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
