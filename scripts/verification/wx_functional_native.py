"""Native-source MCP smoke. This is not container or connected-agent acceptance.

uv run python scripts/verification/wx_functional_native.py [--live] [--output PATH]
--live explicitly enables read-only Open-Meteo calls; default smoke is offline.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import secrets
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import uvicorn
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from percival_weather_mcp import server
from percival_weather_mcp.__version__ import __version__


async def stdio_smoke(live: bool) -> dict:
    report: dict = {"transport": "stdio", "calls": []}
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "percival_weather_mcp", "--mode", "stdio"]
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as client:
        init = await client.initialize()
        assert init.serverInfo.version == __version__
        report["version"] = init.serverInfo.version
        tools = await client.list_tools()
        prompts = await client.list_prompts()
        resources = await client.list_resources()
        templates = await client.list_resource_templates()
        report["counts"] = [
            len(tools.tools),
            len(prompts.prompts),
            len(resources.resources),
            len(templates.resourceTemplates),
        ]
        assert report["counts"] == [9, 3, 3, 1]
        for uri in [
            "weather://codes",
            "weather://aqi",
            "weather://timezones",
            "weather://schema/weather_get_details",
            "weather://schema/weather_get_by_range",
            "weather://schema/weather_get_air_quality_details",
        ]:
            result = await client.read_resource(uri)
            assert json.loads(result.contents[0].text)
        today = datetime.now(timezone.utc).date().isoformat()
        for name, args in [
            ("weather_quick_answer", {"city": "London, UK"}),
            ("weather_analysis", {"city": "London, UK", "start_date": today, "end_date": today}),
            (
                "weather_unit_conversion",
                {
                    "datetime_str": "2026-11-05T12:00:00Z",
                    "from_timezone": "UTC",
                    "to_timezone": "America/Sao_Paulo",
                },
            ),
        ]:
            assert (await client.get_prompt(name, args)).messages

        async def call(name: str, args: dict) -> str:
            result = await client.call_tool(name, args)
            text = result.content[0].text
            assert not result.isError, f"{name}: {text[:500]}"
            report["calls"].append({"tool": name, "passed": True})
            return text

        assert "Upstream readiness not checked" in await call("weather_get_status", {})
        converted = json.loads(
            await call(
                "weather_convert_time",
                {
                    "datetime_str": "2026-11-05T12:00:00Z",
                    "from_timezone": "UTC",
                    "to_timezone": "America/Sao_Paulo",
                },
            )
        )
        assert "09:00:00" in converted["converted_datetime"]
        assert (
            json.loads(await call("weather_get_time", {"timezone_name": "UTC"}))["timezone"]
            == "UTC"
        )
        assert (
            json.loads(await call("weather_get_timezone", {"timezone_name": "America/Sao_Paulo"}))[
                "timezone_name"
            ]
            == "America/Sao_Paulo"
        )
        invalid = await client.call_tool(
            "weather_get_air_quality_details", {"city": "Paris", "variables": []}
        )
        assert invalid.isError and "at least 1" in invalid.content[0].text
        if live:
            assert "UTC" in await call("weather_get_current", {"city": "London, UK"})
            details = json.loads(
                await call("weather_get_details", {"city": "London, UK", "include_forecast": True})
            )
            assert details["location"]["country_code"] == "GB" and details["valid_time"]
            period = json.loads(
                await call(
                    "weather_get_by_range",
                    {
                        "city": "São Paulo, BR",
                        "start_date": today,
                        "end_date": today,
                        "sample_mode": "spread",
                    },
                )
            )
            assert (
                period["location"]["country_code"] == "BR"
                and period["sample"]["returned_points"] <= 12
            )
            for name in ("weather_get_air_quality", "weather_get_air_quality_details"):
                aq = json.loads(
                    await call(name, {"city": "Paris, FR", "variables": ["pm2_5", "ozone"]})
                )
                assert (
                    aq["location"]["country_code"] == "FR" and aq["source"]["data_kind"] == "model"
                )
                assert aq["air_quality_index"]["system"] == "us_aqi"
        report["resources_read"] = 6
        report["prompts_rendered"] = 3
    return report


async def http_smoke() -> dict:
    """Actual HTTP fixture with a reserved loopback socket and ephemeral bearer."""
    server.register_all_tools()
    app = server.create_fastmcp_server(host="127.0.0.1", stateless=True)
    token = secrets.token_urlsafe(32)
    wrapped = server._create_http_transport_app(
        app, mode="streamable-http", auth_token=token, started_at=0.0, version=__version__
    )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        base = f"http://127.0.0.1:{sock.getsockname()[1]}"
        runtime = uvicorn.Server(uvicorn.Config(wrapped, log_level="warning"))
        task = asyncio.create_task(runtime.serve(sockets=[sock]))
        try:
            async with httpx.AsyncClient() as http:
                for _ in range(100):
                    if runtime.started:
                        break
                    await asyncio.sleep(0.02)
                assert runtime.started
                assert (await http.get(base + "/healthz")).status_code == 200
                assert (await http.get(base + "/health")).status_code == 200
                assert (await http.get(base + "/metrics")).status_code == 401
                assert (await http.post(base + "/mcp", json={})).status_code == 401
                assert (
                    await http.get(base + "/metrics", headers={"Authorization": f"Bearer {token}"})
                ).status_code == 200
            async with (
                streamablehttp_client(
                    base + "/mcp", headers={"Authorization": f"Bearer {token}"}
                ) as (read, write, _),
                ClientSession(read, write) as client,
            ):
                assert (await client.initialize()).serverInfo.version == __version__
                assert len((await client.list_tools()).tools) == 9
                result = await client.call_tool(
                    "weather_convert_time",
                    {
                        "datetime_str": "2026-11-05T12:00:00Z",
                        "from_timezone": "UTC",
                        "to_timezone": "America/Sao_Paulo",
                    },
                )
                assert not result.isError and "09:00:00" in result.content[0].text
            return {
                "transport": "streamable-http",
                "bind": "127.0.0.1:ephemeral",
                "healthz": 200,
                "health": 200,
                "unauthorized_mcp": 401,
                "unauthorized_metrics": 401,
                "authorized_metrics": 200,
                "authenticated_mcp_call": "passed",
            }
        finally:
            runtime.should_exit = True
            await asyncio.wait_for(task, timeout=10)


async def run(live: bool) -> dict:
    return {
        "scope": "native-source-not-container",
        "image_id": None,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "live_open_meteo": live,
        "stdio": await stdio_smoke(live),
        "http": await http_smoke(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = asyncio.run(run(args.live))
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
