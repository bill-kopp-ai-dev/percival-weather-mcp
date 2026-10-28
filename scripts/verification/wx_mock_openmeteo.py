#!/usr/bin/env python3
"""Mock HTTPS dos três serviços Open-Meteo (geocoding, forecast, air-quality).

Serve para exercitar os tools do `percival-weather-mcp` sem tocar nos
serviços públicos. O servidor escuta em TLS com certificado gerado
localmente para os hostnames reais, e o container do MCP resolve esses
hostnames para o mock via `--add-host` + `SSL_CERT_FILE`.

Modos (env `MOCK_MODE`):
  ok       -> respostas normais (default)
  500      -> HTTP 500 em toda requisição (testa retry/backoff e erro)
  429      -> HTTP 429 em toda requisição (testa retry por rate limit)
  empty    -> 200 com séries horárias vazias (testa "empty hourly series")
  hang     -> não responde (testa timeout do cliente)

Geocoding: devolve um lugar fictício fixo, exceto quando o nome contém
`notfound` (devolve `results` vazio) ou `offline` (404).
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

MOCK_LAT = -23.5505
MOCK_LON = -46.6333

WEATHER_FIELDS = {
    "temperature_2m": 21.4,
    "relative_humidity_2m": 62.0,
    "dew_point_2m": 13.9,
    "weather_code": 2,
    "wind_speed_10m": 11.2,
    "wind_direction_10m": 135.0,
    "wind_gusts_10m": 18.7,
    "precipitation": 0.0,
    "rain": 0.0,
    "snowfall": 0.0,
    "precipitation_probability": 10.0,
    "pressure_msl": 1014.0,
    "cloud_cover": 40.0,
    "uv_index": 5.2,
    "apparent_temperature": 20.8,
    "visibility": 20000.0,
}

AIR_QUALITY_FIELDS = {
    "pm10": 14.0,
    "pm2_5": 6.5,
    "ozone": 62.0,
    "nitrogen_dioxide": 11.0,
    "carbon_monoxide": 230.0,
    "sulphur_dioxide": 1.2,
    "ammonia": 2.4,
    "dust": 3.1,
    "aerosol_optical_depth": 0.05,
}

_LOG_LOCK = threading.Lock()


def log_request(line: str) -> None:
    path = os.environ.get("MOCK_LOG")
    if not path:
        return
    with _LOG_LOCK, open(path, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def hourly_series(fields: dict[str, float], start: datetime, end: datetime) -> dict[str, list]:
    series: dict[str, list] = {"time": []}
    for name in fields:
        series[name] = []
    cursor = start
    while cursor <= end:
        series["time"].append(cursor.strftime("%Y-%m-%dT%H:%M"))
        for name, value in fields.items():
            series[name].append(value)
        cursor += timedelta(hours=1)
    return series


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        return

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        mode = os.environ.get("MOCK_MODE", "ok")
        log_request(f"{self.headers.get('Host')} {parsed.path}?{parsed.query}")

        if mode == "hang":
            time.sleep(600)
            return
        if mode == "500":
            self._send_json(500, {"reason": "mock forced failure"})
            return
        if mode == "429":
            self._send_json(429, {"reason": "mock forced rate limit"})
            return

        if parsed.path == "/v1/search":
            self._handle_geocoding(query)
        elif parsed.path == "/v1/forecast":
            self._handle_forecast(query, mode)
        elif parsed.path == "/v1/air-quality":
            self._handle_air_quality(query, mode)
        else:
            self._send_json(404, {"reason": f"unknown path {parsed.path}"})

    def _handle_geocoding(self, query: dict[str, list[str]]) -> None:
        name = (query.get("name") or [""])[0]
        if "notfound" in name.lower():
            self._send_json(200, {"generationtime_ms": 0.4})
            return
        if "offline" in name.lower():
            self._send_json(404, {"reason": "mock forced not found"})
            return
        self._send_json(
            200,
            {
                "results": [
                    {
                        "id": 1,
                        "name": "Cidade Ficticia",
                        "latitude": MOCK_LAT,
                        "longitude": MOCK_LON,
                        "country": "Brasil",
                        "country_code": "BR",
                        "admin1": "Estado Ficticio",
                    }
                ],
                "generationtime_ms": 0.8,
            },
        )

    def _handle_forecast(self, query: dict[str, list[str]], mode: str) -> None:
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        start_raw = (query.get("start_date") or [""])[0]
        end_raw = (query.get("end_date") or [""])[0]
        if start_raw and end_raw:
            start = datetime.strptime(start_raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            end = datetime.strptime(end_raw, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(
                hours=23
            )
        else:
            days = int((query.get("forecast_days") or ["1"])[0])
            start = now - timedelta(hours=1)
            end = now + timedelta(hours=24 * days)
        series = hourly_series(WEATHER_FIELDS, start, end)
        if mode == "empty":
            series = {"time": []}
        self._send_json(200, {"latitude": MOCK_LAT, "longitude": MOCK_LON, "hourly": series})

    def _handle_air_quality(self, query: dict[str, list[str]], mode: str) -> None:
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        requested = (query.get("hourly") or [",".join(AIR_QUALITY_FIELDS)])[0]
        names = [name.strip() for name in requested.split(",") if name.strip()]
        fields = {name: AIR_QUALITY_FIELDS.get(name, 1.0) for name in names}
        series = hourly_series(fields, now - timedelta(hours=1), now + timedelta(hours=24))
        if mode == "empty":
            series = {"time": []}
        self._send_json(200, {"latitude": MOCK_LAT, "longitude": MOCK_LON, "hourly": series})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cert", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--port", type=int, default=8443)
    args = parser.parse_args()

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=args.cert, keyfile=args.key)
    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    print(
        f"mock open-meteo ouvindo em 0.0.0.0:{args.port} mode={os.environ.get('MOCK_MODE', 'ok')}",
        flush=True,
    )
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
