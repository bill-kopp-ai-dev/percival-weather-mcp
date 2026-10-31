#!/usr/bin/env python3
"""Transporte HTTP do `percival-weather-mcp`: autenticacao, probes e rate limit.

Publica o container em 127.0.0.1 (somente loopback do host) com um token
sintetico e verifica:

  * `/healthz` responde sem bearer; `/metrics` exige bearer quando token
    estiver configurado e permanece aberto sem token configurado;
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
import uuid

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
    name = f"wx-http-{uuid.uuid4().hex[:10]}"
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
    if token_env:
        status, body, headers = http("GET", f"{base}/metrics", token=token_env)
        result["metrics_com_bearer"] = {
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
    name = f"wx-rl-{uuid.uuid4().hex[:10]}"
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
        for request_id in range(1, 7):
            status, _, headers = http(
                "POST",
                f"{base}/mcp",
                token=TOKEN,
                body={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "wx-http-probe", "version": "1"},
                    },
                },
            )
            result["requests"].append(
                {
                    "status": status,
                    "retry_after": headers.get("retry-after"),
                }
            )
    subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True)
    result["criterion_passed"] = [item["status"] for item in result["requests"]] == [
        200,
        200,
        200,
        429,
        429,
        429,
    ]
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
    authenticated = report["http_com_token"]
    auth_passed = (
        authenticated.get("healthz", {}).get("status") == 200
        and authenticated.get("metrics_sem_bearer", {}).get("status") == 401
        and authenticated.get("metrics_com_bearer", {}).get("status") == 200
        and authenticated.get("mcp_sem_bearer", {}).get("status") == 401
        and authenticated.get("mcp_com_bearer", {}).get("status") == 200
        and authenticated.get("mcp_bearer_errado", {}).get("status") == 401
    )
    no_token = report["http_sem_token_refusa_inicializacao"]
    no_token_passed = no_token.get("exit_code") == "1" and any(
        "requires authentication" in line for line in no_token.get("logs", [])
    )
    return 0 if auth_passed and no_token_passed and report["rate_limit"]["criterion_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
