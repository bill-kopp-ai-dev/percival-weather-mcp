#!/usr/bin/env python3
"""L2 diagnostic: sessão MCP stdio real contra a imagem do percival-weather-mcp.

Conduz a imagem pelo protocolo MCP (initialize -> notifications/initialized
-> tools/list -> prompts/list -> resources/list -> resources/templates/list
-> tools/call) usando o perfil endurecido: rootfs somente leitura, tmpfs em
/tmp, cap_drop ALL, no-new-privileges, UID nao-root e rede controlada.

Os tres servicos Open-Meteo nunca sao contatados de verdade: o mock local
(`wx_mock_openmeteo.py`) responde em TLS e os hostnames publicos sao
resolvidos para o mock via `--add-host`, com `SSL_CERT_FILE` apontando
para a CA local. Sem `--network` a imagem roda sem egress nenhum.

Uso:
  wx_mcp_session.py --image IMAGEM [--network NOME] [--add-host host=ip ...]
                    [--env K=V ...] [--call 'nome|{"json":"args"}']
"""

from __future__ import annotations

import argparse
import json
import selectors
import subprocess
import time


class McpSession:
    """Cliente JSON-RPC/stdio minimo que conduz `docker run -i`."""

    def __init__(self, command: list[str], timeout: float) -> None:
        self.timeout = timeout
        self.stdout_lines: list[str] = []
        self.non_jsonrpc_lines: list[str] = []
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        assert self.process.stdin is not None and self.process.stdout is not None
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)

    def request(self, method: str, params: dict | None, request_id: int) -> dict | None:
        payload: dict = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            payload["params"] = params
        self.process.stdin.write(json.dumps(payload) + "\n")
        self.process.stdin.flush()
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if not self.selector.select(max(deadline - time.monotonic(), 0.1)):
                continue
            line = self.process.stdout.readline()
            if not line:
                return None
            self.stdout_lines.append(line)
            try:
                decoded = json.loads(line)
            except json.JSONDecodeError:
                self.non_jsonrpc_lines.append(line[:200])
                return None
            if decoded.get("id") == request_id:
                return decoded
        return None

    def notify(self, method: str, params: dict | None = None) -> None:
        payload: dict = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        self.process.stdin.write(json.dumps(payload) + "\n")
        self.process.stdin.flush()

    def close_stdin(self) -> int:
        self.process.stdin.close()
        try:
            return self.process.wait(timeout=30)
        except subprocess.TimeoutExpired as exc:
            self.process.kill()
            self.process.wait()
            raise RuntimeError("container nao encerrou apos o fechamento do stdin") from exc

    def drain_stdout(self) -> None:
        trailing = self.process.stdout.read()
        for line in trailing.splitlines():
            if not line.strip():
                continue
            self.stdout_lines.append(line + "\n")
            try:
                json.loads(line)
            except json.JSONDecodeError:
                self.non_jsonrpc_lines.append(line[:200])

    def stderr_text(self) -> str:
        return self.process.stderr.read()


def build_command(args: argparse.Namespace) -> list[str]:
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
    ]
    if args.certs_dir:
        command += [
            "--mount",
            f"type=bind,source={args.certs_dir},destination=/certs,ro",
            "--env",
            "SSL_CERT_FILE=/certs/ca.pem",
        ]
    for item in args.add_host:
        command += ["--add-host", item]
    for item in args.env:
        key, _, value = item.partition("=")
        command += ["--env", f"{key}={value}"]
    command.append(args.image)
    return command


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--network", default="none")
    parser.add_argument("--user", default="999:999")
    parser.add_argument("--certs-dir", default=None)
    parser.add_argument("--add-host", action="append", default=[])
    parser.add_argument("--env", action="append", default=[])
    parser.add_argument("--call", action="append", default=[])
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()

    command = build_command(args)
    session = McpSession(command, args.timeout)
    report: dict = {"command": command, "calls": []}

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
        report["initialize"] = init["result"]
        session.notify("notifications/initialized", {})

        tools = session.request("tools/list", {}, 2)
        tool_list = (tools or {}).get("result", {}).get("tools")
        if not isinstance(tool_list, list) or not tool_list:
            raise RuntimeError("tools/list falhou")
        report["tool_count"] = len(tool_list)
        report["tool_names"] = sorted(t.get("name", "") for t in tool_list)
        report["tool_schemas"] = {
            t.get("name"): sorted((t.get("inputSchema") or {}).get("properties", {}).keys())
            for t in tool_list
        }

        prompts = session.request("prompts/list", {}, 3)
        report["prompt_count"] = len((prompts or {}).get("result", {}).get("prompts", []) or [])
        report["prompt_names"] = sorted(
            p.get("name", "") for p in (prompts or {}).get("result", {}).get("prompts", []) or []
        )
        resources = session.request("resources/list", {}, 4)
        report["resource_count"] = len(
            (resources or {}).get("result", {}).get("resources", []) or []
        )
        report["resource_uris"] = sorted(
            r.get("uri", "") for r in (resources or {}).get("result", {}).get("resources", []) or []
        )
        templates = session.request("resources/templates/list", {}, 5)
        report["resource_template_count"] = len(
            (templates or {}).get("result", {}).get("resourceTemplates", []) or []
        )
        report["resource_template_uris"] = sorted(
            t.get("uriTemplate", "")
            for t in (templates or {}).get("result", {}).get("resourceTemplates", []) or []
        )

        request_id = 100
        for spec in args.call:
            name, _, raw_args = spec.partition("|")
            try:
                call_args = json.loads(raw_args) if raw_args else {}
            except json.JSONDecodeError:
                call_args = {}
            request_id += 1
            payload = session.request(
                "tools/call",
                {"name": name, "arguments": call_args},
                request_id,
            )
            result = (payload or {}).get("result", {})
            text = ""
            content = result.get("content") or []
            if content and isinstance(content[0], dict):
                text = content[0].get("text", "") or ""
            report["calls"].append(
                {
                    "tool": name,
                    "arguments": call_args,
                    "is_error": result.get("isError"),
                    "text_head": text[:800],
                    "text_len": len(text),
                }
            )

        report["exit_code"] = session.close_stdin()
        session.drain_stdout()
        report["stderr_tail"] = session.stderr_text().strip().splitlines()[-14:]
    except Exception as exc:
        report["failure"] = f"{type(exc).__name__}: {exc}"
        if session.process.poll() is None:
            session.process.kill()
            session.process.wait()
        report["stderr_tail"] = session.stderr_text().strip().splitlines()[-14:]
    finally:
        session.selector.close()

    report["stdout_line_count"] = len(session.stdout_lines)
    report["stdout_non_jsonrpc_lines"] = session.non_jsonrpc_lines
    report["stdout_is_jsonrpc_only"] = not session.non_jsonrpc_lines
    print(json.dumps(report, indent=2, ensure_ascii=False))
    failed = "failure" in report
    print("RESULT:", "FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
