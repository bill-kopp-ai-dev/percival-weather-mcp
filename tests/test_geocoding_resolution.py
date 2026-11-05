"""R2: never discard a qualifier; retain immutable identity through shared cache."""

import json

import pytest
import respx

from percival_weather_mcp.errors import NoDataError
from percival_weather_mcp.tools.geocoding_service import GeocodingService
from percival_weather_mcp.tools.tools_air_quality import GetAirQualityToolHandler
from percival_weather_mcp.tools.tools_weather import GetWeatherDetailsToolHandler

URL = GeocodingService.BASE_URL


@pytest.mark.parametrize(
    "query,code",
    [
        ("London, UK", "GB"),
        ("London, GB", "GB"),
        ("São Paulo, BR", "BR"),
        ("São Paulo, Brazil", "BR"),
        ("São Paulo, Brasil", "BR"),
        ("Paris, FR", "FR"),
        ("Lisbon, Portugal", "PT"),
        ("London, Reino Unido", "GB"),
    ],
)
async def test_country_fallback_is_filtered_bounded_and_cache_keeps_identity(query, code):
    name = query.split(",")[0]
    with respx.mock as mock:
        native = mock.get(
            URL, params={"name": query, "count": 10, "language": "en", "format": "json"}
        ).respond(200, json={})
        filtered = mock.get(
            URL,
            params={
                "name": name,
                "count": 10,
                "language": "en",
                "format": "json",
                "countryCode": code,
            },
        ).respond(
            200,
            json={
                "results": [
                    {
                        "id": 123,
                        "name": name,
                        "country_code": code,
                        "country": "Selected country",
                        "admin1": "Region",
                        "timezone": "UTC",
                        "latitude": 1.0,
                        "longitude": 2.0,
                    },
                ]
            },
        )
        first = await GeocodingService().resolve(query)
        cached = await GeocodingService().resolve(query.upper())
    assert native.call_count == filtered.call_count == 1
    assert first == cached
    assert first.selected.country_code == code and first.selected.id == 123
    assert first.context()["resolution"]["country_filter"] == code


@pytest.mark.parametrize(
    "query,region",
    [
        ("Springfield, IL", "Illinois"),
        ("Washington, D.C.", "District of Columbia"),
        ("Springfield, CA", "California"),
    ],
)
async def test_region_alias_takes_native_precedence(query, region):
    with respx.mock as mock:
        route = mock.get(URL).respond(
            200,
            json={
                "results": [
                    {
                        "name": query.split(",")[0],
                        "admin1": region,
                        "country_code": "US",
                        "latitude": 1.0,
                        "longitude": 2.0,
                    }
                ]
            },
        )
        result = await GeocodingService().resolve(query)
    assert route.call_count == 1
    assert result.selected.admin1 == region and result.selected.country_code == "US"


async def test_wrong_country_never_silently_resolves_to_portugal():
    with respx.mock as mock:
        route = mock.get(URL).respond(
            200,
            json={
                "results": [
                    {"name": "Lisbon", "country_code": "PT", "latitude": 1.0, "longitude": 2.0}
                ]
            },
        )
        with pytest.raises(NoDataError, match="qualifier was not discarded"):
            await GeocodingService().resolve("Lisbon, UK")
    assert route.call_count == 2
    assert route.calls[1].request.url.params["countryCode"] == "GB"


async def test_unknown_qualifier_is_not_retried_without_filter():
    with respx.mock as mock:
        route = mock.get(URL).respond(200, json={})
        with pytest.raises(NoDataError):
            await GeocodingService().resolve("Springfield, Unknownland")
    assert route.call_count == 1


async def test_ambiguous_context_shared_by_weather_and_aq_without_extra_geocoding():
    candidates = [
        {
            "name": "Springfield",
            "admin1": region,
            "country": "United States",
            "country_code": "US",
            "latitude": float(i),
            "longitude": 2.0,
        }
        for i, region in enumerate(("Illinois", "Missouri", "Ohio", "Oregon", "Kentucky"))
    ]
    with respx.mock as mock:
        geo = mock.get(URL).respond(200, json={"results": candidates})
        mock.get("https://api.open-meteo.com/v1/forecast").respond(
            200, json={"hourly": {"time": ["2026-11-05T21:00"], "weather_code": [0]}}
        )
        mock.get("https://air-quality-api.open-meteo.com/v1/air-quality").respond(
            200, json={"hourly": {"time": ["2026-11-05T21:00"], "pm10": [0]}}
        )
        weather = json.loads(
            (await GetWeatherDetailsToolHandler().run_tool({"city": "Springfield"}))[0].text
        )
        aq = json.loads(
            (
                await GetAirQualityToolHandler().run_tool(
                    {"city": "Springfield", "variables": ["pm10"]}
                )
            )[0].text
        )
    assert geo.call_count == 1
    assert weather["location"] == aq["location"]
    assert weather["resolution"] == aq["resolution"]
    assert aq["resolution"]["ambiguous"] and aq["resolution"]["candidate_count"] == 5
    assert len(aq["resolution"]["alternatives"]) == 3
    assert not aq["resolution"]["uniqueness_guaranteed"]


async def test_qualified_countries_do_not_contaminate_cache():
    with respx.mock as mock:
        mock.get(URL, params={"name": "Paris, FR"}).respond(
            200, json={"results": [{"country_code": "FR", "latitude": 1.0, "longitude": 2.0}]}
        )
        mock.get(URL, params={"name": "Paris, US"}).respond(
            200, json={"results": [{"country_code": "US", "latitude": 3.0, "longitude": 4.0}]}
        )
        fr = await GeocodingService().resolve("Paris, FR")
        us = await GeocodingService().resolve("Paris, US")
    assert fr.selected.country_code == "FR" and us.selected.country_code == "US"
