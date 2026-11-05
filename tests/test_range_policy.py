"""R3: local UTC policy, with no I/O for dates that cannot be served."""

from datetime import datetime, timedelta, timezone

import pytest
import respx

from percival_weather_mcp import config, series
from percival_weather_mcp.errors import InvalidRequestError, UpstreamError
from percival_weather_mcp.http_client import ResilientHttpClient
from percival_weather_mcp.range_policy import validate_range
from percival_weather_mcp.tools.tools_weather import GetWeatherByDateRangeToolHandler

REFERENCE = datetime(2026, 11, 5, 21, 20, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "offset,accepted", [(-93, False), (-92, True), (0, True), (15, True), (16, False)]
)
async def test_window_boundaries_before_any_io(monkeypatch, offset, accepted):
    monkeypatch.setattr(series, "utc_now", lambda: REFERENCE)
    day = (REFERENCE + timedelta(days=offset)).date().isoformat()
    if accepted:
        assert validate_range(day, day) == (day, day)
    else:
        with respx.mock(assert_all_called=False) as mock:
            with pytest.raises(InvalidRequestError, match="2026-08-05 through 2026-11-20"):
                await GetWeatherByDateRangeToolHandler().run_tool(
                    {"city": "Test", "start_date": day, "end_date": day}
                )
            assert not mock.calls


@pytest.mark.parametrize(
    "start,end,rule",
    [
        ("2020-01-01", "2020-01-02", "window"),
        ("2030-01-01", "2030-01-02", "window"),
        ("2026-11-20", "2026-11-05", "on or after"),
        ("2026-11-04", "2026-11-20", "16 days"),
        ("2026-02-30", "2026-03-01", "YYYY-MM-DD"),
    ],
)
async def test_actionable_rejections_without_geocoding(monkeypatch, start, end, rule):
    monkeypatch.setattr(series, "utc_now", lambda: REFERENCE)
    with respx.mock(assert_all_called=False) as mock:
        with pytest.raises(InvalidRequestError, match=rule):
            await GetWeatherByDateRangeToolHandler().run_tool(
                {"city": "Test", "start_date": start, "end_date": end}
            )
        assert not mock.calls


def test_duration_leap_day_and_utc_year_rollover(monkeypatch):
    assert validate_range("2026-11-05", "2026-11-20", reference=REFERENCE)
    assert validate_range(
        "2024-02-29", "2024-03-01", reference=datetime(2024, 3, 1, tzinfo=timezone.utc)
    )
    assert validate_range(
        "2025-12-31", "2026-01-01", reference=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    monkeypatch.setattr(config, "_runtime_settings", config.Settings(max_date_range_days=2))
    with pytest.raises(InvalidRequestError, match="2 days"):
        validate_range("2026-11-05", "2026-11-07", reference=REFERENCE)


@pytest.mark.parametrize(
    "body,json_body",
    [
        ("<html>not JSON</html>", False),
        ({}, True),
        ({"reason": ["not a string"]}, True),
        ({"reason": "Date out\nside\x00 window" + "x" * 400}, True),
    ],
)
async def test_400_reason_is_bounded_sanitized_and_not_retried(body, json_body):
    with respx.mock as mock:
        route = mock.get("https://api.open-meteo.com/v1/forecast").respond(
            400, **({"json": body} if json_body else {"text": body})
        )
        async with ResilientHttpClient() as client:
            with pytest.raises(UpstreamError) as info:
                await client.get_json("https://api.open-meteo.com/v1/forecast")
    assert route.call_count == 1 and info.value.status_code == 400
    text = str(info.value)
    assert "check the location" not in text
    assert "\n" not in text and "\x00" not in text
    if isinstance(body, dict) and isinstance(body.get("reason"), str):
        assert "Provider reason:" in text
        assert len(text.split("Provider reason: ")[1]) <= 300
    else:
        assert "Provider reason:" not in text
