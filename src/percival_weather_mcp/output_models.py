"""Models used both to validate JSON responses and generate resource schemas."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .series import AQ_SAMPLE_LIMIT, WEATHER_SAMPLE_LIMIT, SampleMode


class OutputModel(BaseModel):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)


class Statistics(OutputModel):
    min: float | None
    max: float | None
    avg: float | None
    valid_points: int
    missing_points: int


class Segment(OutputModel):
    hourly_points: int
    variables: dict[str, Statistics]


class Coverage(OutputModel):
    reference_time: str
    timezone: Literal["UTC"]
    start_time: str | None
    end_time: str | None
    returned_points: int
    expected_points: int | None
    partial: bool
    variables: dict[str, Statistics]
    segments: dict[str, Segment]


class Sample(OutputModel):
    mode: SampleMode
    limit: int
    returned_points: int
    total_points: int
    truncated: bool


class WeatherRow(OutputModel):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False, strict=True)
    time: str | None = None
    temperature_c: float | None = None
    relative_humidity_percent: float | None = None
    humidity_percent: float | None = None
    dew_point_c: float | None = None
    weather_code: int | None = None
    weather_description: str | None = None
    wind_speed_kmh: float | None = None
    wind_direction_degrees: float | None = None
    wind_gusts_kmh: float | None = None
    precipitation_mm: float | None = None
    rain_mm: float | None = None
    snowfall_cm: float | None = None
    precipitation_probability_percent: float | None = None
    pressure_hpa: float | None = None
    cloud_cover_percent: float | None = None
    uv_index: float | None = None
    apparent_temperature_c: float | None = None
    visibility_m: float | None = None


class LocationResponse(OutputModel):
    city: str | None
    latitude: float | None
    longitude: float | None
    location: dict[str, Any] = Field(default_factory=dict)
    resolution: dict[str, Any] = Field(default_factory=dict)
    source: dict[str, str] = Field(default_factory=dict)


class WeatherDetails(LocationResponse, WeatherRow):
    selection_method: Literal["nearest_hour"]
    reference_time: str
    valid_time: str | None
    timezone: Literal["UTC"]
    forecast: list[WeatherRow] | None = None


class Period(OutputModel):
    start_date: str | None
    end_date: str | None
    hourly_points: int


class WeatherRange(LocationResponse):
    period: Period
    summary: dict[str, Any]
    summary_scope: Literal["entire_returned_window"]
    coverage: Coverage
    sample: Sample
    hourly_sample: list[WeatherRow] = Field(max_length=WEATHER_SAMPLE_LIMIT)


class AirQualityDetails(LocationResponse):
    current_air_quality: dict[str, Any]
    selection_method: Literal["nearest_hour"]
    reference_time: str
    timezone: Literal["UTC"]
    air_quality_index: dict[str, Any]
    coverage: Coverage
    full_data: dict[str, Any]  # Raw provider object, intentionally open and untruncated.


class AirQualityCompact(LocationResponse):
    current_air_quality: dict[str, Any] | None
    selection_method: Literal["nearest_hour"]
    reference_time: str
    timezone: Literal["UTC"]
    air_quality_index: dict[str, Any]
    coverage: Coverage
    summary: dict[str, Any]
    summary_scope: Literal["entire_returned_window"]
    sample: Sample
    hourly_sample: list[dict[str, Any]] = Field(max_length=AQ_SAMPLE_LIMIT)


def compact_json(payload: Any) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def serialize(model: type[OutputModel], payload: Any) -> str:
    from pydantic import ValidationError

    from .errors import UpstreamError

    try:
        return compact_json(
            model.model_validate(payload).model_dump(mode="json", exclude_unset=True)
        )
    except (ValidationError, ValueError) as exc:
        raise UpstreamError(
            "Upstream model data cannot be represented by the output contract.",
            service="upstream",
            reason="invalid_response",
        ) from exc
