"""R3/R5: aligned denominators, temporal segments and bounded representative samples."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from percival_weather_mcp import series, utils

REFERENCE = datetime(2026, 11, 5, 21, 20, tzinfo=timezone.utc)


def times(total):
    start = REFERENCE.replace(hour=0, minute=0)
    return [(start + timedelta(hours=i)).isoformat() for i in range(total)]


def test_120_points_28_missing_are_not_120_observations():
    hourly = {"time": times(120), "ammonia": [None] * 28 + [1] * 92}
    data = series.series_metadata(hourly, ["ammonia"], reference=REFERENCE, expected_points=120)
    assert data["variables"]["ammonia"] == {
        "min": 1,
        "max": 1,
        "avg": 1,
        "valid_points": 92,
        "missing_points": 28,
    }
    assert data["partial"]
    assert data["segments"]["past_or_present"]["hourly_points"] == 22
    assert data["segments"]["future"]["hourly_points"] == 98
    assert data["segments"]["past_or_present"]["variables"]["ammonia"]["avg"] is None


def test_short_invalid_and_zero_values_keep_temporal_alignment():
    values = [None, False, True, float("nan"), float("inf"), float("-inf"), 0, 7]
    data = series.series_metadata(
        {"time": times(10), "pm10": values}, ["pm10", "absent"], reference=REFERENCE
    )
    assert data["variables"]["pm10"] == {
        "min": 0,
        "max": 7,
        "avg": 3.5,
        "valid_points": 2,
        "missing_points": 8,
    }
    assert data["variables"]["absent"]["avg"] is None
    assert data["variables"]["absent"]["missing_points"] == 10


def test_equal_reference_is_past_present_and_nearest_can_be_future():
    data = series.series_metadata(
        {"time": ["2026-11-05T21:20Z", "2026-11-05T22:00Z"], "pm10": [1, 2]},
        ["pm10"],
        reference=REFERENCE,
    )
    assert data["segments"]["past_or_present"]["hourly_points"] == 1
    assert (
        utils.get_closest_utc_index(
            ["2026-11-05T21:00Z", "2026-11-05T22:00Z"], reference=REFERENCE + timedelta(minutes=20)
        )
        == 1
    )


@pytest.mark.parametrize("total", [1, 12, 24, 384])
@pytest.mark.parametrize("mode", ["first", "last", "spread"])
def test_sampling_is_bounded_ordered_and_covers_expected_ends(total, mode):
    rows = [
        {"time": t, "temperature_c": i, "precipitation_mm": 0} for i, t in enumerate(times(total))
    ]
    payload = json.loads(
        utils.format_get_weather_bytime(
            {"city": "São Paulo", "weather_data": rows, "sample_mode": mode}
        )
    )
    values = [r["temperature_c"] for r in payload["hourly_sample"]]
    assert len(values) == min(total, 12)
    assert values == sorted(set(values))
    if total <= 12 or mode == "first":
        assert values[0] == 0
    if total <= 12 or mode in {"last", "spread"}:
        assert values[-1] == total - 1
    if mode == "spread":
        assert values[0] == 0
    assert payload["sample"]["truncated"] == (total > 12)
    assert payload["summary"]["temperature_c"]["valid_points"] == total


def test_default_sample_keeps_first_12_and_total_summary_is_explicit():
    rows = [{"time": t, "temperature_c": i} for i, t in enumerate(times(24))]
    payload = json.loads(utils.format_get_weather_bytime({"city": "Test", "weather_data": rows}))
    assert payload["hourly_sample"][-1]["temperature_c"] == 11
    assert payload["summary"]["temperature_c"]["max"] == 23
    assert payload["summary_scope"] == "entire_returned_window"
