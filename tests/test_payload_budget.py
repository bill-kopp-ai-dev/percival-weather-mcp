"""Reproducible 120h x 9 pollutant payload; details may never silently truncate."""

import json
from datetime import datetime, timedelta, timezone

import pytest
import respx

from percival_weather_mcp import series
from percival_weather_mcp.air_quality_index import SUBINDICES
from percival_weather_mcp.models import EXTENDED_AIR_QUALITY_VARIABLES
from percival_weather_mcp.output_models import compact_json
from percival_weather_mcp.tools.tools_air_quality import GetAirQualityDetailsToolHandler


def payload_fixture():
    start = datetime(2026, 11, 5, tzinfo=timezone.utc)
    hourly = {"time": [(start + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(120)]}
    for variable in EXTENDED_AIR_QUALITY_VARIABLES:
        hourly[variable] = [
            None if variable == "ammonia" and i < 28 else round(i / 10, 1) for i in range(120)
        ]
    for key in SUBINDICES.values():
        hourly[key] = [42] * 120
    return {
        "latitude": 1.0,
        "longitude": 2.0,
        "hourly": hourly,
        "provider_extra": {"kept": "intact"},
    }


async def test_details_payload_equivalence_and_measured_bytes(monkeypatch):
    monkeypatch.setattr(
        series, "utc_now", lambda: datetime(2026, 11, 5, 21, 20, tzinfo=timezone.utc)
    )
    raw = payload_fixture()
    with respx.mock as mock:
        mock.get("https://geocoding-api.open-meteo.com/v1/search").respond(
            200,
            json={
                "results": [
                    {"name": "São Paulo", "country_code": "BR", "latitude": 1.0, "longitude": 2.0}
                ]
            },
        )
        mock.get("https://air-quality-api.open-meteo.com/v1/air-quality").respond(200, json=raw)
        text = (await GetAirQualityDetailsToolHandler().run_tool({"city": "São Paulo"}))[0].text
    payload = json.loads(text)
    assert payload["full_data"] == raw
    assert "São Paulo" in text and "\\u00e3" not in text
    compact = len(text.encode("utf-8"))
    indented = len(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
    )
    assert compact < indented
    # Measured 14,378 compact / 35,232 indented bytes on the final fixture.
    # Rounded 16 KiB ceiling leaves ~14% for non-destructive metadata evolution.
    assert compact <= 16 * 1024
    print(f"PAYLOAD_BYTES compact={compact} indented={indented}")


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_json_never_emits_nonstandard_nan_or_infinity(value):
    with pytest.raises(ValueError):
        compact_json({"value": value})
