"""Pydantic models used as MCP tool input/output contracts.

These models are the single source of truth for tool parameter validation. The
FastMCP integration derives the JSON schema directly from the ``Field``
annotations, replacing the previous dynamic signature builder.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------


class GetCurrentWeatherInput(BaseModel):
    city: str = Field(
        ...,
        description=(
            "City name in English, optionally with region/country to disambiguate "
            "(for example: 'Springfield, US' or 'London, UK')."
        ),
    )


class GetWeatherByDateRangeInput(BaseModel):
    city: str = Field(
        ...,
        description="City name in English, optionally with region/country to disambiguate.",
    )
    start_date: str = Field(
        ...,
        description="Start date in ISO 8601 calendar format: YYYY-MM-DD.",
    )
    end_date: str = Field(
        ...,
        description=(
            "End date in ISO 8601 calendar format: YYYY-MM-DD. "
            "Must be the same day or after start_date."
        ),
    )


class GetWeatherDetailsInput(BaseModel):
    city: str = Field(
        ...,
        description="City name in English, optionally with region/country to disambiguate.",
    )
    include_forecast: bool = Field(
        False,
        description=(
            "If true, include the next ~24 hours under the 'forecast' key. "
            "Defaults to false for smaller responses."
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
    )
    variables: list[AirQualityVariable] | None = Field(
        default=None,
        description=(
            "Optional subset of pollutant variables. "
            "If omitted, defaults to: pm10, pm2_5, ozone, nitrogen_dioxide, carbon_monoxide."
        ),
    )


class GetAirQualityDetailsInput(BaseModel):
    city: str = Field(
        ...,
        description="City name in English, optionally with region/country to disambiguate.",
    )
    variables: list[AirQualityVariable] | None = Field(
        default=None,
        description=(
            "Optional pollutant list. If omitted, uses an extended default set "
            "covering major pollutants and particulates."
        ),
    )


# ---------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------


class GetCurrentDateTimeInput(BaseModel):
    timezone_name: str = Field(
        ...,
        min_length=1,
        description=(
            "IANA timezone name (for example: 'America/New_York', 'Europe/London', 'UTC')."
        ),
    )

    @field_validator("timezone_name")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class GetTimeZoneInfoInput(BaseModel):
    timezone_name: str = Field(
        ...,
        min_length=1,
        description="IANA timezone name (for example: 'America/Sao_Paulo', 'Asia/Tokyo').",
    )

    @field_validator("timezone_name")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class ConvertTimeInput(BaseModel):
    datetime_str: str = Field(
        ...,
        description=(
            "Datetime to convert: 'now' or ISO 8601 string "
            "(for example: '2026-03-28T14:30:00' or '2026-03-28T14:30:00Z'). "
            "If timezone is omitted, it is interpreted in from_timezone."
        ),
    )
    from_timezone: str = Field(..., description="Source timezone (IANA name).")
    to_timezone: str = Field(..., description="Target timezone (IANA name).")


# ---------------------------------------------------------------------------
# Generic status
# ---------------------------------------------------------------------------


class StatusOutput(BaseModel):
    status: str
    server: str
    version: str
