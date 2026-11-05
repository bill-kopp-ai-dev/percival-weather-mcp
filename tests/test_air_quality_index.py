"""R4: index bands and mass concentrations must never be interchangeable."""

import json

import pytest
import respx

from percival_weather_mcp.air_quality_index import category, index_payload, reference_payload
from percival_weather_mcp.presentation import AirQualityFormatter
from percival_weather_mcp.tools.tools_air_quality import GetAirQualityToolHandler


@pytest.mark.parametrize(
    "value,label",
    [
        (0, "Good"),
        (50, "Good"),
        (50.01, "Moderate"),
        (100, "Moderate"),
        (100.01, "Unhealthy for Sensitive Groups"),
        (150, "Unhealthy for Sensitive Groups"),
        (150.01, "Unhealthy"),
        (200, "Unhealthy"),
        (200.01, "Very Unhealthy"),
        (300, "Very Unhealthy"),
        (300.01, "Hazardous"),
        (500, "Hazardous"),
        (501, "Hazardous"),
        (None, None),
        (-1, None),
        (float("nan"), None),
        (float("inf"), None),
        (True, None),
    ],
)
def test_index_categories_and_resource_agree(value, label):
    assert category(value) == label
    if label and value <= 500:
        bands = reference_payload()["bands"]["pm2_5"]
        band = next(
            b
            for b in bands
            if (b["min_exclusive"] is None or value > b["min_exclusive"]) and value <= b["max"]
        )
        assert band["label"] == label


def test_missing_unsupported_and_beyond_scale_are_explicit():
    data = index_payload(
        {"us_aqi_pm10": 501}, ["pm10", "pm2_5", "ammonia", "dust", "aerosol_optical_depth"]
    )
    assert data["pollutants"]["pm10"]["beyond_scale"]
    assert data["pollutants"]["pm2_5"]["status"] == "unavailable"
    assert all(
        data["pollutants"][p]["status"] == "not_supported"
        for p in ("ammonia", "dust", "aerosol_optical_depth")
    )
    assert "subset" in data["scope"] or data["scope"] == "requested_pollutant_subindices_only"


@pytest.mark.parametrize("concentration", [35.4, 250.4, 300])
async def test_provider_subindex_controls_label_not_raw_pm25(concentration):
    with respx.mock as mock:
        mock.get("https://geocoding-api.open-meteo.com/v1/search").respond(
            200, json={"results": [{"latitude": 1.0, "longitude": 2.0}]}
        )
        aq = mock.get("https://air-quality-api.open-meteo.com/v1/air-quality").respond(
            200,
            json={
                "hourly": {
                    "time": ["2026-11-05T21:00"],
                    "pm2_5": [concentration],
                    "us_aqi_pm2_5": [42],
                }
            },
        )
        result = json.loads(
            (await GetAirQualityToolHandler().run_tool({"city": "Test", "variables": ["pm2_5"]}))[
                0
            ].text
        )
    assert aq.call_count == 1
    assert aq.calls[0].request.url.params["hourly"] == "pm2_5,us_aqi_pm2_5"
    assert result["air_quality_index"]["pollutants"]["pm2_5"]["category"] == "Good"
    assert result["current_air_quality"]["pm2_5"] == concentration
    legacy = AirQualityFormatter().format_legacy("Test", 1.0, 2.0, {"pm2_5": concentration})
    assert "Good" not in legacy and "Unhealthy" not in legacy and "Health Advice" not in legacy
