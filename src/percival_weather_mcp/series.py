"""UTC-aligned model-series statistics and deterministic sampling."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Literal

SampleMode = Literal["first", "last", "spread"]
WEATHER_SAMPLE_LIMIT = 12
AQ_SAMPLE_LIMIT = 8


def utc_now() -> datetime:
    """Single clock boundary, replaceable in deterministic tests."""
    return datetime.now(timezone.utc)


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (
        parsed.replace(tzinfo=timezone.utc)
        if parsed.tzinfo is None
        else parsed.astimezone(timezone.utc)
    )


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def value_at(values: Any, index: int) -> Any:
    return values[index] if isinstance(values, list) and index < len(values) else None


def statistics(values: list[Any]) -> dict[str, Any]:
    valid = [float(v) for v in values if is_number(v)]
    return {
        "min": round(min(valid), 2) if valid else None,
        "max": round(max(valid), 2) if valid else None,
        "avg": round(sum(valid) / len(valid), 2) if valid else None,
        "valid_points": len(valid),
        "missing_points": len(values) - len(valid),
    }


def sample_indices(total: int, limit: int, mode: SampleMode = "first") -> list[int]:
    if total <= limit:
        return list(range(total))
    if mode == "last":
        return list(range(total - limit, total))
    if mode == "spread":
        return [i * (total - 1) // (limit - 1) for i in range(limit)]
    return list(range(limit))


def sample_metadata(total: int, limit: int, mode: SampleMode = "first") -> dict[str, Any]:
    return {
        "mode": mode,
        "limit": limit,
        "returned_points": min(total, limit),
        "total_points": total,
        "truncated": total > limit,
    }


def series_metadata(
    hourly: dict[str, Any],
    variables: list[str],
    *,
    reference: datetime,
    expected_points: int | None = None,
) -> dict[str, Any]:
    """Missing/short arrays never shift data relative to the returned time axis."""
    times = hourly.get("time") or []
    moments = [parse_utc(t) for t in times]
    groups = {
        "past_or_present": [i for i, t in enumerate(moments) if t <= reference],
        "future": [i for i, t in enumerate(moments) if t > reference],
    }

    def stats(indices: list[int]) -> dict[str, Any]:
        return {
            key: statistics([value_at(hourly.get(key), i) for i in indices]) for key in variables
        }

    all_stats = stats(list(range(len(times))))
    return {
        "reference_time": reference.isoformat(),
        "timezone": "UTC",
        "start_time": moments[0].isoformat() if moments else None,
        "end_time": moments[-1].isoformat() if moments else None,
        "returned_points": len(times),
        "expected_points": expected_points,
        "partial": (expected_points is not None and len(times) != expected_points)
        or any(s["missing_points"] for s in all_stats.values()),
        "variables": all_stats,
        "segments": {
            name: {"hourly_points": len(indices), "variables": stats(indices)}
            for name, indices in groups.items()
        },
    }


def provenance(kind: str) -> dict[str, str]:
    return {
        "provider": "Open-Meteo",
        "data_kind": "model",
        "product": "Forecast API" if kind == "weather" else "CAMS air-quality forecasts",
        "reference": "https://open-meteo.com/en/docs"
        + ("/air-quality-api" if kind != "weather" else ""),
        "attribution": "Open-Meteo" if kind == "weather" else "Open-Meteo / CAMS ENSEMBLE",
    }
