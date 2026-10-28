#!/usr/bin/env python3
"""Matriz de configuracao do `percival-weather-mcp` (nivel de container).

Executa a imagem com combinacoes de ambiente/argumentos e registra codigo
de saida e ultimas linhas do stderr. Cobre:

  * recusas do entrypoint e do bootstrap (timeout/port invalidos);
  * politica de seguranca do transporte HTTP (recusa sem token em host
    nao-loopback, aceitacao em loopback);
  * `MCP_TRANSPORT` invalido (deve degradar ou recusar, nunca expor HTTP);
  * parametros de retry negativos;
  * validacao de entrada das tools (cidade vazia, caracteres proibidos,
    cidade longa, timezone invalida) via sessao MCP real.

Uso:
  wx_config_matrix.py --image IMAGEM [--network NOME] [--certs-dir DIR]
                      [--add-host host=ip ...]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time

from wx_mcp_session import McpSession

CONTAINER_CASES = [
    {"name": "baseline_stdio", "env": [], "expect": "roda"},
    {"name": "timeout_invalido", "env": ["MCP_WEATHER_HTTP_TIMEOUT=abc"], "expect": "recusa"},
    {"name": "port_invalido", "env": ["PORT=nao-numero"], "expect": "recusa"},
    {"name": "http_sem_token", "env": ["MCP_TRANSPORT=http"], "expect": "recusa"},
    {"name": "http_loopback_sem_token", "env": ["MCP_TRANSPORT=http-loopback"], "expect": "sobe"},
    {"name": "transport_invalido", "env": ["MCP_TRANSPORT=htpp"], "expect": "degrada"},
    {
        "name": "retries_negativos",
        "env": ["MCP_WEATHER_HTTP_MAX_RETRIES=-1"],
        "expect": "recusa na 1a tool",
    },
    {"name": "rate_limit_zero", "env": ["MCP_WEATHER_RATE_LIMIT_PER_MINUTE=0"], "expect": "sobe"},
    {"name": "metrics_desligado", "env": ["MCP_WEATHER_ENABLE_METRICS=false"], "expect": "sobe"},
    {"name": "log_json", "env": ["MCP_WEATHER_LOG_FORMAT=json"], "expect": "sobe"},
]


def _base_docker_args(network: str, user: str) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "-i",
        "--init",
        "--network",
        network,
        "--read-only",
        "--tmpfs",
        "/tmp:size=64m,mode=1777,noexec,nosuid,nodev",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--user",
        user,
    ]


def run_container_case(image: str, case: dict, network: str, user: str, timeout: float) -> dict:
    """Casos que devem recusar: execucao em primeiro plano com stdin fechado.

    Casos que devem subir sao tratados por `run_live_case`.
    """
    command = _base_docker_args(network, user)
    for item in case["env"]:
        command += ["--env", item]
    command.append(image)

    started = time.monotonic()
    process = subprocess.Popen(
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    try:
        out, err = process.communicate(input="", timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        out, err = process.communicate()
        return {
            "case": case["name"],
            "expect": case["expect"],
            "exit_code": None,
            "duration_s": round(time.monotonic() - started, 2),
            "note": "nao encerrou no tempo limite",
            "stderr_tail": err.strip().splitlines()[-6:],
        }
    return {
        "case": case["name"],
        "expect": case["expect"],
        "exit_code": process.returncode,
        "duration_s": round(time.monotonic() - started, 2),
        "stdout_head": out[:200],
        "stderr_tail": err.strip().splitlines()[-6:],
    }


def run_live_case(image: str, case: dict, network: str, user: str) -> dict:
    """Casos que devem continuar no ar: container destacado + inspecao + limpeza."""
    name = f"iac-wx-{case['name']}"
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
        network,
        "--read-only",
        "--tmpfs",
        "/tmp:size=64m,mode=1777,noexec,nosuid,nodev",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--user",
        user,
    ]
    for item in case["env"]:
        command += ["--env", item]
    command.append(image)
    subprocess.run(command, check=True, capture_output=True)
    time.sleep(5)
    inspected = subprocess.run(
        [
            "docker",
            "inspect",
            "-f",
            "{{.State.Status}}|{{.State.ExitCode}}|{{json .NetworkSettings.Ports}}",
            name,
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    ).stdout.strip()
    logs = subprocess.run(
        ["docker", "logs", name],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    ).stdout
    subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True)
    status, _, remainder = inspected.partition("|")
    exit_code, _, ports = remainder.partition("|")
    return {
        "case": case["name"],
        "expect": case["expect"],
        "status": status,
        "exit_code": exit_code,
        "published_ports": ports,
        "transport_log": [line for line in logs.splitlines() if "Starting" in line][-2:],
        "stderr_tail": logs.strip().splitlines()[-4:],
    }


INPUT_CASES = [
    {"name": "city_vazia", "tool": "weather_get_current", "args": {"city": ""}},
    {
        "name": "city_caracteres_proibidos",
        "tool": "weather_get_current",
        "args": {"city": "Sao <Paulo>"},
    },
    {"name": "city_longa", "tool": "weather_get_current", "args": {"city": "A" * 250}},
    {
        "name": "timezone_invalida",
        "tool": "weather_get_time",
        "args": {"timezone_name": "Mars/Olympus"},
    },
    {
        "name": "timezone_caractere_proibido",
        "tool": "weather_get_timezone",
        "args": {"timezone_name": "UTC; rm -rf /"},
    },
    {
        "name": "range_invertido",
        "tool": "weather_get_by_range",
        "args": {"city": "Cidade Teste", "start_date": "2026-10-20", "end_date": "2026-10-10"},
    },
    {
        "name": "range_longo",
        "tool": "weather_get_by_range",
        "args": {"city": "Cidade Teste", "start_date": "2026-01-01", "end_date": "2026-12-31"},
    },
    {
        "name": "data_formato_errado",
        "tool": "weather_get_by_range",
        "args": {"city": "Cidade Teste", "start_date": "20/10/2026", "end_date": "21/10/2026"},
    },
    {
        "name": "datetime_invalido",
        "tool": "weather_convert_time",
        "args": {
            "datetime_str": "ontem",
            "from_timezone": "UTC",
            "to_timezone": "America/Sao_Paulo",
        },
    },
]


def run_input_case(
    image: str,
    case: dict,
    network: str,
    user: str,
    certs: str | None,
    add_host: list[str],
    timeout: float,
) -> dict:
    command = [
        "docker",
        "run",
        "--rm",
        "-i",
        "--init",
        "--network",
        network,
        "--read-only",
        "--tmpfs",
        "/tmp:size=64m,mode=1777,noexec,nosuid,nodev",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--user",
        user,
    ]
    if certs:
        command += [
            "--mount",
            f"type=bind,source={certs},destination=/certs,ro",
            "--env",
            "SSL_CERT_FILE=/certs/ca.pem",
        ]
    for item in add_host:
        command += ["--add-host", item]
    command.append(image)

    session = McpSession(command, timeout)
    result: dict = {"case": case["name"]}
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
            "tools/call", {"name": case["tool"], "arguments": case["args"]}, 101
        )
        payload = payload or {}
        tool_result = payload.get("result", {})
        content = tool_result.get("content") or []
        text = content[0].get("text", "") if content and isinstance(content[0], dict) else ""
        result["is_error"] = tool_result.get("isError")
        result["text_head"] = text[:300]
        result["exit_code"] = session.close_stdin()
    except Exception as exc:
        result["failure"] = f"{type(exc).__name__}: {exc}"
        if session.process.poll() is None:
            session.process.kill()
            session.process.wait()
    finally:
        session.selector.close()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--network", default="none")
    parser.add_argument("--user", default="999:999")
    parser.add_argument("--certs-dir", default=None)
    parser.add_argument("--add-host", action="append", default=[])
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    report: dict = {"container_cases": [], "input_cases": []}
    for case in CONTAINER_CASES:
        if case["expect"] == "recusa":
            report["container_cases"].append(
                run_container_case(args.image, case, args.network, args.user, args.timeout)
            )
        else:
            report["container_cases"].append(
                run_live_case(args.image, case, args.network, args.user)
            )
    for case in INPUT_CASES:
        report["input_cases"].append(
            run_input_case(
                args.image,
                case,
                args.network,
                args.user,
                args.certs_dir,
                args.add_host,
                args.timeout,
            )
        )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
