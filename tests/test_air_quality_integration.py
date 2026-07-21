"""End-to-end smoke tests for the air-quality handlers using respx mocks."""

from __future__ import annotations

import pytest
import respx


@pytest.fixture
def _mock_open_meteo():
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://geocoding-api.open-meteo.com/v1/search").respond(
            200,
            json={"results": [{"latitude": 1.0, "longitude": 2.0}]},
        )
        mock.get("https://air-quality-api.open-meteo.com/v1/air-quality").respond(
            200,
            json={
                "hourly": {
                    "time": ["2026-01-01T00:00", "2026-01-01T01:00"],
                    "pm2_5": [1.0, 2.0],
                    "pm10": [3.0, 4.0],
                    "ozone": [10.0, 12.0],
                }
            },
        )
        yield mock


@pytest.mark.asyncio
async def test_get_air_quality_handler_runs_end_to_end(_mock_open_meteo):
    from percival_weather_mcp.tools.tools_air_quality import GetAirQualityToolHandler

    handler = GetAirQualityToolHandler()
    result = await handler.run_tool({"city": "Lisbon"})
    assert result
    text = result[0].text
    assert "Lisbon" in text
    # Mocked pm2_5 max should appear in the summary section.
    assert "pm2_5" in text


@pytest.mark.asyncio
async def test_get_air_quality_details_handler_runs_end_to_end(_mock_open_meteo):
    from percival_weather_mcp.tools.tools_air_quality import (
        GetAirQualityDetailsToolHandler,
    )

    handler = GetAirQualityDetailsToolHandler()
    result = await handler.run_tool({"city": "Lisbon"})
    assert result
    import json

    payload = json.loads(result[0].text)
    assert payload["city"] == "Lisbon"
    assert payload["latitude"] == 1.0
    assert payload["longitude"] == 2.0
