"""Regression tests for the error taxonomy and the outbound retry policy.

Two behaviours are pinned here because they were the root cause of F-001 and
F-002 in the IaC readiness report:

* a failure of the upstream must never reach the agent as "invalid input";
* a status that cannot change on a second attempt must not be repeated.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from percival_weather_mcp import config
from percival_weather_mcp.errors import (
    InvalidRequestError,
    NoDataError,
    UpstreamError,
)
from percival_weather_mcp.http_client import ResilientHttpClient, reset_shared_state

BASE_URL = "https://example.test"


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    """Use a deterministic retry budget and disable the shared breaker."""
    reset_shared_state()
    monkeypatch.setattr(
        config,
        "_runtime_settings",
        config.Settings.from_env(
            http_max_retries=2,
            http_backoff_base=0.001,
            http_backoff_cap=0.002,
            http_max_concurrency=4,
        ),
        raising=False,
    )
    yield
    reset_shared_state()


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_404_is_answered_on_the_first_attempt():
    """A deterministic rejection must not be repeated against the upstream."""
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.get("/missing").respond(404)
        async with ResilientHttpClient(name="test") as client:
            with pytest.raises(UpstreamError) as excinfo:
                await client.get_json(f"{BASE_URL}/missing")
    assert route.call_count == 1
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_400_is_answered_on_the_first_attempt():
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.get("/rejected").respond(400)
        async with ResilientHttpClient(name="test") as client:
            with pytest.raises(UpstreamError):
                await client.get_json(f"{BASE_URL}/rejected")
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_429_is_retried_up_to_the_configured_limit():
    """A rate-limited upstream is transient: the retry budget applies."""
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.get("/limited").respond(429)
        async with ResilientHttpClient(name="test") as client:
            with pytest.raises(UpstreamError) as excinfo:
                await client.get_json(f"{BASE_URL}/limited")
    assert route.call_count == 3  # 1 attempt + 2 retries
    assert excinfo.value.status_code == 429


@pytest.mark.asyncio
async def test_500_is_retried_up_to_the_configured_limit():
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.get("/boom").respond(500)
        async with ResilientHttpClient(name="test") as client:
            with pytest.raises(UpstreamError):
                await client.get_json(f"{BASE_URL}/boom")
    assert route.call_count == 3


@pytest.mark.asyncio
async def test_timeout_is_retried_and_reported_as_a_timeout():
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.get("/slow").mock(side_effect=httpx.ReadTimeout("timed out"))
        async with ResilientHttpClient(name="test") as client:
            with pytest.raises(UpstreamError) as excinfo:
                await client.get_json(f"{BASE_URL}/slow")
    assert route.call_count == 3
    assert excinfo.value.reason == "timeout"
    assert "timed out" in str(excinfo.value)


@pytest.mark.asyncio
async def test_non_json_body_is_reported_as_an_invalid_upstream_response():
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("/garbage").respond(200, text="<html>not json</html>")
        async with ResilientHttpClient(name="test") as client:
            with pytest.raises(UpstreamError) as excinfo:
                await client.get_json(f"{BASE_URL}/garbage")
    assert excinfo.value.reason == "invalid_response"


# ---------------------------------------------------------------------------
# Message quality: the agent must receive the true cause
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limit_message_names_the_status_and_the_orientation():
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("/limited").respond(429)
        async with ResilientHttpClient(name="geocoding") as client:
            with pytest.raises(UpstreamError) as excinfo:
                await client.get_json(f"{BASE_URL}/limited")
    message = str(excinfo.value)
    assert "429" in message
    assert "Too Many Requests" in message
    assert "rate limiting" in message
    assert "Invalid" not in message


@pytest.mark.asyncio
async def test_not_found_message_points_at_the_city_name():
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("/missing").respond(404)
        async with ResilientHttpClient(name="geocoding") as client:
            with pytest.raises(UpstreamError) as excinfo:
                await client.get_json(f"{BASE_URL}/missing")
    message = str(excinfo.value)
    assert "404" in message
    assert "city name" in message


# ---------------------------------------------------------------------------
# Handler level: the taxonomy must survive the tool layer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handler_reports_upstream_failure_as_an_upstream_failure():
    """F-001 regression: a 500 from Open-Meteo must not say "invalid request"."""
    from percival_weather_mcp.tools.tools_weather import GetCurrentWeatherToolHandler

    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://geocoding-api.open-meteo.com/v1/search").respond(
            200, json={"results": [{"latitude": 1.0, "longitude": 2.0}]}
        )
        mock.get("https://api.open-meteo.com/v1/forecast").respond(500)

        handler = GetCurrentWeatherToolHandler()
        with pytest.raises(UpstreamError) as excinfo:
            await handler.run_tool({"city": "Lisbon"})

    message = str(excinfo.value)
    assert "HTTP 500" in message
    assert "retry shortly" in message
    assert "Invalid weather request" not in message


@pytest.mark.asyncio
async def test_handler_keeps_invalid_input_as_invalid_input():
    """A locally rejected request keeps the "invalid input" wording."""
    from percival_weather_mcp.tools.tools_weather import GetCurrentWeatherToolHandler

    handler = GetCurrentWeatherToolHandler()
    with pytest.raises(InvalidRequestError) as excinfo:
        await handler.run_tool({"city": ""})

    message = str(excinfo.value)
    assert "Invalid weather request" in message
    assert "Upstream" not in message


@pytest.mark.asyncio
async def test_empty_geocoding_result_is_not_reported_as_an_invalid_request():
    """A 200 without results is neither an upstream failure nor invalid input."""
    from percival_weather_mcp.tools.tools_weather import GetCurrentWeatherToolHandler

    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://geocoding-api.open-meteo.com/v1/search").respond(
            200, json={"generationtime_ms": 0.4}
        )

        handler = GetCurrentWeatherToolHandler()
        with pytest.raises(NoDataError) as excinfo:
            await handler.run_tool({"city": "Atlantis"})

    message = str(excinfo.value)
    assert "No location found" in message
    assert "Invalid weather request" not in message


@pytest.mark.asyncio
async def test_empty_hourly_series_is_not_reported_as_an_invalid_request():
    """A 200 with an empty series is a "no data" outcome, not a failure."""
    from percival_weather_mcp.tools.tools_weather import GetCurrentWeatherToolHandler

    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://geocoding-api.open-meteo.com/v1/search").respond(
            200, json={"results": [{"latitude": 1.0, "longitude": 2.0}]}
        )
        mock.get("https://api.open-meteo.com/v1/forecast").respond(
            200, json={"hourly": {"time": []}}
        )

        handler = GetCurrentWeatherToolHandler()
        with pytest.raises(NoDataError) as excinfo:
            await handler.run_tool({"city": "Lisbon"})

    message = str(excinfo.value)
    assert "empty hourly series" in message
    assert "Invalid weather request" not in message


@pytest.mark.asyncio
async def test_empty_air_quality_series_is_reported_as_no_data():
    from percival_weather_mcp.tools.tools_air_quality import GetAirQualityToolHandler

    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://geocoding-api.open-meteo.com/v1/search").respond(
            200, json={"results": [{"latitude": 1.0, "longitude": 2.0}]}
        )
        mock.get("https://air-quality-api.open-meteo.com/v1/air-quality").respond(
            200, json={"hourly": {"time": []}}
        )

        handler = GetAirQualityToolHandler()
        with pytest.raises(NoDataError) as excinfo:
            await handler.run_tool({"city": "Lisbon"})

    message = str(excinfo.value)
    assert "empty hourly series" in message
    assert "Invalid air quality request" not in message


@pytest.mark.asyncio
async def test_the_message_names_the_service_that_failed():
    """One HTTP client can serve two upstreams: the label must follow the call."""
    from percival_weather_mcp.tools.tools_air_quality import GetAirQualityToolHandler

    with respx.mock(assert_all_called=False) as mock:
        # The air-quality tools geocode and read the air-quality endpoint
        # through the same client; a geocoding failure must say so.
        mock.get("https://geocoding-api.open-meteo.com/v1/search").respond(500)

        handler = GetAirQualityToolHandler()
        with pytest.raises(UpstreamError) as excinfo:
            await handler.run_tool({"city": "Lisbon"})

    message = str(excinfo.value)
    assert "Open-Meteo geocoding" in message
    assert "air quality" not in message
