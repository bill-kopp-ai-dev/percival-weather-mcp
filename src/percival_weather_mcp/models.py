"""Pydantic models used as MCP tool input contracts.

The detailed output shape and error conditions for each tool are documented
in the tool's ``description`` (returned by ``get_tool_description()``); the
models below only carry parameter-level metadata (description, examples,
length and pattern constraints) so the schema does not duplicate information.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------


class GetCurrentWeatherInput(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"city": "London, UK"},
                {"city": "New York"},
                {"city": "São Paulo, BR"},
            ]
        }
    )

    city: str = Field(
        ...,
        description=(
            "City name in English, optionally with region/country to disambiguate "
            "(for example: 'Springfield, US' or 'London, UK'). Control characters, "
            "angle brackets and excessive whitespace are stripped automatically."
        ),
        examples=["London, UK", "New York"],
        min_length=1,
        max_length=200,
    )


class GetWeatherByDateRangeInput(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"city": "Lisbon", "start_date": "2026-03-01", "end_date": "2026-03-07"},
            ]
        }
    )

    city: str = Field(
        ...,
        description="City name in English, optionally with region/country to disambiguate.",
        min_length=1,
        max_length=200,
    )
    start_date: str = Field(
        ...,
        description=(
            "Start date in ISO 8601 calendar format: YYYY-MM-DD. Must be on "
            "or before end_date."
        ),
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    end_date: str = Field(
        ...,
        description=(
            "End date in ISO 8601 calendar format: YYYY-MM-DD (inclusive). "
            "The total range (end_date - start_date + 1) must be <= 16 days."
        ),
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )


class GetWeatherDetailsInput(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"city": "Berlin", "include_forecast": True}]}
    )

    city: str = Field(
        ...,
        description="City name in English, optionally with region/country to disambiguate.",
        min_length=1,
        max_length=200,
    )
    include_forecast: bool = Field(
        False,
        description=(
            "When true, attaches a 'forecast' array with the next 24 hours of "
            "hourly observations. Defaults to false for a smaller payload."
        ),
    )


# ---------------------------------------------------------------------------
# Air quality
# ---------------------------------------------------------------------------


AirQualityVariable = Literal[
    "pm10",
    "pm2_5",
    "carbon_monoxide",
    "nitrogen_dioxide",
    "ozone",
    "sulphur_dioxide",
    "ammonia",
    "dust",
    "aerosol_optical_depth",
]

DEFAULT_AIR_QUALITY_VARIABLES: list[AirQualityVariable] = [
    "pm10",
    "pm2_5",
    "ozone",
    "nitrogen_dioxide",
    "carbon_monoxide",
]

EXTENDED_AIR_QUALITY_VARIABLES: list[AirQualityVariable] = [
    "pm10",
    "pm2_5",
    "ozone",
    "nitrogen_dioxide",
    "carbon_monoxide",
    "sulphur_dioxide",
    "ammonia",
    "dust",
    "aerosol_optical_depth",
]


class GetAirQualityInput(BaseModel):
    city: str = Field(
        ...,
        description="City name in English, optionally with region/country to disambiguate.",
        examples=["London", "São Paulo, BR"],
        min_length=1,
        max_length=200,
    )
    variables: list[AirQualityVariable] | None = Field(
        default=None,
        description=(
            "Optional subset of pollutant variables to query. If omitted, the "
            "default compact set is used: pm10, pm2_5, ozone, nitrogen_dioxide, "
            "carbon_monoxide. Pass an explicit list when the user asks for a "
            "specific pollutant (e.g. ['ozone']) or wants to exclude one."
        ),
        examples=[["pm2_5", "pm10"], ["ozone"]],
    )


class GetAirQualityDetailsInput(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"city": "Beijing"},
                {"city": "São Paulo", "variables": ["pm2_5", "ozone"]},
            ]
        }
    )

    city: str = Field(
        ...,
        description="City name in English, optionally with region/country to disambiguate.",
        examples=["Beijing", "São Paulo"],
        min_length=1,
        max_length=200,
    )
    variables: list[AirQualityVariable] | None = Field(
        default=None,
        description=(
            "Optional pollutant list. If omitted, the extended default set is "
            "used: pm10, pm2_5, ozone, nitrogen_dioxide, carbon_monoxide, "
            "sulphur_dioxide, ammonia, dust, aerosol_optical_depth."
        ),
        examples=[["pm2_5", "ozone"]],
    )


# ---------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------


class GetCurrentDateTimeInput(BaseModel):
    timezone_name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description=(
            "IANA timezone name (for example: 'America/New_York', 'Europe/London', 'UTC'). "
            "Case-sensitive; must match the IANA database exactly. Refer to the "
            "``weather://timezones`` resource for the curated list."
        ),
        examples=["America/Sao_Paulo", "Europe/London", "UTC"],
    )

    @field_validator("timezone_name")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class GetTimeZoneInfoInput(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"timezone_name": "America/Sao_Paulo"}]}
    )

    timezone_name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description=(
            "IANA timezone name (for example: 'America/Sao_Paulo', 'Asia/Tokyo'). "
            "Refer to ``weather://timezones`` for the curated list."
        ),
        examples=["America/Sao_Paulo", "Asia/Tokyo"],
    )

    @field_validator("timezone_name")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class ConvertTimeInput(BaseModel):
    datetime_str: str = Field(
        ...,
        description=(
            "Datetime to convert. Either the literal string 'now' (case-insensitive, "
            "whitespace allowed) or an ISO 8601 datetime (e.g. '2026-03-28T14:30:00', "
            "'2026-03-28T14:30:00Z', or '2026-03-28T14:30:00+02:00'). Strings without an "
            "offset are interpreted in ``from_timezone``."
        ),
        examples=["now", "2026-03-28T14:30:00", "2026-03-28T14:30:00Z"],
    )
    from_timezone: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Source timezone (IANA name).",
    )
    to_timezone: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Target timezone (IANA name).",
    )


# ---------------------------------------------------------------------------
# Generic status
# ---------------------------------------------------------------------------


class StatusOutput(BaseModel):
    status: str
    server: str
    version: str