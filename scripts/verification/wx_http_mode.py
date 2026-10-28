#!/usr/bin/env python3
"""Transporte HTTP do `percival-weather-mcp`: autenticacao, probes e rate limit.

Publica o container em 127.0.0.1 (somente loopback do host) com um token
sintetico e verifica:

  * `/healthz` e `/metrics` respondem **sem** bearer (bypass intencional do
    middleware de saude);
  * `/mcp` sem bearer responde 401 e com bearer responde 200;
  * o handshake MCP completo funciona sobre streamable-http;
  * o rate limit por IP devolve 429 com `Retry-After`;
  * `http-loopback` sobe sem token (uso local documentado).

Uso:
  wx_http_mode.py --image IMAGEM [--host-port 18080] [--token TOKEN]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.error
import urllib.request

TOKEN = "iac-diag-token-0123456789abcdef0123456789abcdef"


def http(
    method: str,
    url: str,
    token: str | None = None,
    body: dict | None = None,
    extra_headers: dict | None = None,
) -> tuple[int, str, dict]:
    headers = {"Accept": "application/json, text/event-stream"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        headers["Content-Type"] = "application/json"
    if extra_headers:
        headers.update(extra_headers)
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read().decode()[:800], dict(response.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()[:800], dict(exc.headers)
    except Exception as exc:
        return 0, f"{type(exc).__name__}: {exc}", {}


def wait_for(url: str, attempts: int = 20) -> bool:
    for _ in range(attempts):
        status, _, _ = http("GET", url)
        if status:
            return True
        time.sleep(0.5)
    return False


def run_http_case(image: str, port: int, token_env: str | None, rate_limit: str | None) -> dict:
    name = "iac-wx-http"
    subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True)
    command = [
        "docker",
        "run",
        "-d",
        "--init",
        "--name",
        name,
        "-p",
        f"127.0.0.1:{port}:8080",
        "--read-only",
        "--tmpfs",
        "/tmp:size=64m,mode=1777,noexec,nosuid,nodev",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--user",
        "999:999",
        "-e",
        "MCP_TRANSPORT=http",
    ]
    if token_env:
        command += ["-e", f"MCP_WEATHER_AUTH_TOKEN={token_env}"]
    if rate_limit:
        command += ["-e", f"MCP_WEATHER_RATE_LIMIT_PER_MINUTE={rate_limit}"]
    command.append(image)
    subprocess.run(command, check=True, capture_output=True)

    base = f"http://127.0.0.1:{port}"
    result: dict = {"mode": "http", "token_present": bool(token_env)}
    if not wait_for(f"{base}/healthz"):
        logs = subprocess.run(
            ["docker", "logs", name], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        ).stdout
        code = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.ExitCode}}", name], capture_output=True, text=True
        ).stdout.strip()
        subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True)
        return {
            "error": "servidor HTTP nao ficou acessivel",
            "exit_code": code,
            "logs": logs.strip().splitlines()[-10:],
        }

    status, body, _ = http("GET", f"{base}/healthz")
    result["healthz"] = {"status": status, "body": body[:200]}
    status, body, headers = http("GET", f"{base}/metrics")
    result["metrics_sem_bearer"] = {
        "status": status,
        "content_type": headers.get("content-type", ""),
        "sample": [line for line in body.splitlines() if line.startswith("mcp_")][:3],
    }
    status, body, _ = http(
        "POST",
        f"{base}/mcp",
        body={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "iac-diag", "version": "0.1.0"},
            },
        },
    )
    result["mcp_sem_bearer"] = {"status": status, "body": body[:200]}
    if token_env:
        status, body, _ = http(
            "POST",
            f"{base}/mcp",
            token=token_env,
            body={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "iac-diag", "version": "0.1.0"},
                },
            },
        )
        result["mcp_com_bearer"] = {"status": status, "body": body[:400]}
        status, body, _ = http(
            "POST",
            f"{base}/mcp",
            token="token-errado",
            body={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "iac-diag", "version": "0.1.0"},
                },
            },
        )
        result["mcp_bearer_errado"] = {"status": status, "body": body[:120]}
    logs = subprocess.run(
        ["docker", "logs", name], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    ).stdout
    result["log_lines"] = logs.strip().splitlines()[-6:]
    subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True)
    return result


def run_rate_limit_case(image: str, port: int) -> dict:
    name = "iac-wx-rl"
    subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True)
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--init",
            "--name",
            name,
            "-p",
            f"127.0.0.1:{port}:8080",
            "--read-only",
            "--tmpfs",
            "/tmp:size=64m,mode=1777,noexec,nosuid,nodev",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--user",
            "999:999",
            "-e",
            "MCP_TRANSPORT=http",
            "-e",
            f"MCP_WEATHER_AUTH_TOKEN={TOKEN}",
            "-e",
            "MCP_WEATHER_RATE_LIMIT_PER_MINUTE=3",
            image,
        ],
        check=True,
        capture_output=True,
    )
    base = f"http://127.0.0.1:{port}"
    result: dict = {"budget_per_minute": 3, "requests": []}
    if wait_for(f"{base}/healthz"):
        for _ in range(6):
            status, _, headers = http("GET", f"{base}/mcp", token=TOKEN)
            result["requests"].append(
                {
                    "status": status,
                    "retry_after": headers.get("retry-after"),
                }
            )
    subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--host-port", type=int, default=18080)
    parser.add_argument("--token", default=TOKEN)
    args = parser.parse_args()

    report = {
        "http_com_token": run_http_case(args.image, args.host_port, args.token, None),
        "http_sem_token_refusa_inicializacao": run_http_case(
            args.image, args.host_port + 1, None, None
        ),
        "rate_limit": run_rate_limit_case(args.image, args.host_port + 2),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
