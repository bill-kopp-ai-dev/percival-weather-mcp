#!/usr/bin/env python3
"""Cache de geocodificacao do `percival-weather-mcp` (por handler, em memoria).

Sequencia exercitada na MESMA sessao MCP:
  1. weather_get_current  (cidade A)
  2. weather_get_current  (cidade A de novo)  -> deve reusar o cache do handler
  3. weather_get_details  (cidade A)          -> outro handler, cache proprio
  4. weather_get_current  (cidade B)          -> cidade diferente

Conta as requisicoes que o mock recebeu em `/v1/search` (geocoding) e
`/v1/forecast`, atribuindo cada uma a um passo.

Uso:
  wx_cache_probe.py --image IMAGEM --network NOME --mock-ip IP
                    --certs-dir DIR --logs-dir DIR
"""

from __future__ import annotations

import argparse
import json
import os

from wx_mcp_session import McpSession

CALLS = [
    ("passo-1", "weather_get_current", {"city": "Cidade Alfa"}),
    ("passo-2", "weather_get_current", {"city": "Cidade Alfa"}),
    ("passo-3", "weather_get_details", {"city": "Cidade Alfa"}),
    ("passo-4", "weather_get_current", {"city": "Cidade Beta"}),
]


def read_log(logs_dir: str) -> list[str]:
    path = os.path.join(logs_dir, "mock.log")
    try:
        with open(path, encoding="utf-8") as handle:
            return [line.strip() for line in handle if line.strip()]
    except FileNotFoundError:
        return []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--network", required=True)
    parser.add_argument("--mock-ip", required=True)
    parser.add_argument("--certs-dir", required=True)
    parser.add_argument("--logs-dir", required=True)
    parser.add_argument("--user", default="999:999")
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()

    add_host = [
        f"api.open-meteo.com:{args.mock_ip}",
        f"geocoding-api.open-meteo.com:{args.mock_ip}",
        f"air-quality-api.open-meteo.com:{args.mock_ip}",
    ]
    command = [
        "docker",
        "run",
        "--rm",
        "-i",
        "--init",
        "--network",
        args.network,
        "--read-only",
        "--tmpfs",
        "/tmp:size=64m,mode=1777,noexec,nosuid,nodev",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--user",
        args.user,
        "--mount",
        f"type=bind,source={args.certs_dir},destination=/certs,ro",
        "--env",
        "SSL_CERT_FILE=/certs/ca.pem",
    ]
    for item in add_host:
        command += ["--add-host", item]
    command.append(args.image)

    before = len(read_log(args.logs_dir))
    session = McpSession(command, args.timeout)
    report: dict = {"steps": []}
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
        request_id = 200
        for label, tool, tool_args in CALLS:
            request_id += 1
            mark = len(read_log(args.logs_dir))
            payload = session.request(
                "tools/call", {"name": tool, "arguments": tool_args}, request_id
            )
            payload = payload or {}
            result = payload.get("result", {})
            content = result.get("content") or []
            text = content[0].get("text", "") if content and isinstance(content[0], dict) else ""
            new_lines = read_log(args.logs_dir)[mark:]
            report["steps"].append(
                {
                    "step": label,
                    "tool": tool,
                    "arguments": tool_args,
                    "is_error": result.get("isError"),
                    "upstream_calls": [
                        line.split(" ")[1].split("?")[0] for line in new_lines if " " in line
                    ],
                    "text_head": text[:120],
                }
            )
        report["exit_code"] = session.close_stdin()
    except Exception as exc:
        report["failure"] = f"{type(exc).__name__}: {exc}"
        if session.process.poll() is None:
            session.process.kill()
            session.process.wait()
    finally:
        session.selector.close()

    total = read_log(args.logs_dir)[before:]
    report["total_upstream_calls"] = len(total)
    report["total_by_path"] = {
        path: sum(1 for line in total if f" {path}?" in line)
        for path in {line.split(" ")[1].split("?")[0] for line in total if " " in line}
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
