"""Build validated compact views while keeping detailed upstream data intact."""

from collections import Counter
from datetime import date
from typing import Any

from .. import series
from ..air_quality_index import index_payload
from ..models import EXTENDED_AIR_QUALITY_VARIABLES
from ..output_models import AirQualityCompact, WeatherRange, serialize


def weather_range(data: dict[str, Any]) -> str:
    rows = data.get("weather_data") or []
    summary_keys = [
        "temperature_c",
        "apparent_temperature_c",
        "precipitation_mm",
        "wind_speed_kmh",
        "uv_index",
    ]
    numeric_keys = list(
        dict.fromkeys(
            summary_keys
            + [key for row in rows for key in row if key not in {"time", "weather_description"}]
        )
    )
    hourly = {
        "time": [r["time"] for r in rows],
        **{key: [r.get(key) for r in rows] for key in numeric_keys},
    }
    expected = None
    if data.get("start_date") and data.get("end_date"):
        expected = (
            date.fromisoformat(data["end_date"]) - date.fromisoformat(data["start_date"])
        ).days * 24 + 24
    coverage = series.series_metadata(
        hourly,
        numeric_keys,
        reference=series.parse_utc(data["reference_time"])
        if data.get("reference_time")
        else series.utc_now(),
        expected_points=expected,
    )
    mode = data.get("sample_mode", "first")
    conditions = Counter(r.get("weather_description") for r in rows if r.get("weather_description"))
    return serialize(
        WeatherRange,
        {
            "city": data.get("city"),
            "latitude": data.get("latitude"),
            "longitude": data.get("longitude"),
            "location": data.get("location", {}),
            "resolution": data.get("resolution", {}),
            "source": data.get("source", series.provenance("weather")),
            "period": {
                "start_date": data.get("start_date"),
                "end_date": data.get("end_date"),
                "hourly_points": len(rows),
            },
            "summary": {
                **{key: coverage["variables"][key] for key in summary_keys},
                "top_conditions": conditions.most_common(3),
            },
            "summary_scope": "entire_returned_window",
            "coverage": coverage,
            "sample": series.sample_metadata(len(rows), series.WEATHER_SAMPLE_LIMIT, mode),
            "hourly_sample": [
                rows[i] for i in series.sample_indices(len(rows), series.WEATHER_SAMPLE_LIMIT, mode)
            ],
        },
    )


def air_quality(data: dict[str, Any]) -> str:
    hourly = (data.get("full_data") or {}).get("hourly") or {}
    times = hourly.get("time") or []
    pollutants: list[str] = [p for p in EXTENDED_AIR_QUALITY_VARIABLES if p in hourly]
    coverage = data.get("coverage") or series.series_metadata(
        hourly, pollutants, reference=series.utc_now()
    )
    current = data.get("current_air_quality") or {}
    return serialize(
        AirQualityCompact,
        {
            "city": data.get("city"),
            "latitude": data.get("latitude"),
            "longitude": data.get("longitude"),
            "location": data.get("location", {}),
            "resolution": data.get("resolution", {}),
            "source": data.get("source", series.provenance("air-quality")),
            "current_air_quality": current,
            "selection_method": "nearest_hour",
            "reference_time": coverage["reference_time"],
            "timezone": "UTC",
            "air_quality_index": data.get("air_quality_index")
            or index_payload(current, pollutants),
            "coverage": coverage,
            "summary_scope": "entire_returned_window",
            "summary": {"hourly_points": len(times), "pollutants": coverage["variables"]},
            "sample": series.sample_metadata(len(times), series.AQ_SAMPLE_LIMIT),
            "hourly_sample": [
                {"time": times[i], **{p: series.value_at(hourly.get(p), i) for p in pollutants}}
                for i in range(min(len(times), series.AQ_SAMPLE_LIMIT))
            ],
        },
    )
