#!/usr/bin/env python3
"""Recursos, resource templates e prompts do `percival-weather-mcp`.

Le, na mesma sessao MCP: os 3 resources estaticos, um resource template
(`weather://schema/{tool_name}`) e os 3 prompts. O objetivo e verificar que
o contrato declarado em `mcp.yaml` e no rotulo OCI realmente responde.

Uso:
  wx_resources_probe.py --image IMAGEM [--network NOME] [--certs-dir DIR]
                        [--add-host host=ip ...]
"""

from __future__ import annotations

import argparse
import json

from wx_mcp_session import McpSession


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--network", default="none")
    parser.add_argument("--user", default="999:999")
    parser.add_argument("--certs-dir", default=None)
    parser.add_argument("--add-host", action="append", default=[])
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

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
    command.append(args.image)

    session = McpSession(command, args.timeout)
    report: dict = {"resources": [], "resource_templates": [], "prompts": []}
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

        request_id = 300
        for uri in [
            "weather://codes",
            "weather://aqi",
            "weather://timezones",
            "weather://schema/weather_get_details",
            "weather://schema/weather_get_by_range",
            "weather://schema/weather_get_air_quality_details",
            "weather://schema/weather_get_current",
            "weather://schema/inexistente",
        ]:
            request_id += 1
            payload = session.request("resources/read", {"uri": uri}, request_id) or {}
            result = payload.get("result") or {}
            contents = result.get("contents") or []
            text = ""
            if contents and isinstance(contents[0], dict):
                text = contents[0].get("text", "") or ""
            report["resources"].append(
                {
                    "uri": uri,
                    "is_error": result.get("isError"),
                    "rpc_error": (payload.get("error") or {}).get("message"),
                    "mime_type": contents[0].get("mimeType") if contents else None,
                    "text_len": len(text),
                    "text_head": text[:200],
                }
            )

        prompt_calls = [
            ("weather_quick_answer", {}),
            ("weather_quick_answer", {"city": "Cidade Teste"}),
            ("weather_analysis", {}),
            (
                "weather_analysis",
                {"city": "Cidade Teste", "start_date": "2026-10-20", "end_date": "2026-10-21"},
            ),
            ("weather_unit_conversion", {}),
        ]
        for name, prompt_args in prompt_calls:
            request_id += 1
            payload = (
                session.request("prompts/get", {"name": name, "arguments": prompt_args}, request_id)
                or {}
            )
            result = payload.get("result") or {}
            messages = result.get("messages") or []
            report["prompts"].append(
                {
                    "name": name,
                    "arguments": prompt_args,
                    "is_error": result.get("isError"),
                    "rpc_error": (payload.get("error") or {}).get("message"),
                    "message_count": len(messages),
                    "text_head": (
                        messages[0].get("content", {}).get("text", "")[:200]
                        if messages and isinstance(messages[0].get("content"), dict)
                        else ""
                    ),
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
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
