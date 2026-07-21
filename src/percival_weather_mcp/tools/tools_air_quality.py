"""Air quality tool handlers for the MCP weather server."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import cast

from mcp.types import EmbeddedResource, ImageContent, TextContent, Tool

from .. import utils
from ..http_client import ResilientHttpClient
from ..models import (
    DEFAULT_AIR_QUALITY_VARIABLES,
    EXTENDED_AIR_QUALITY_VARIABLES,
    GetAirQualityDetailsInput,
    GetAirQualityInput,
)
from ..presentation import AirQualityFormatter
from .air_quality_service import AirQualityService
from .toolhandler import ToolHandler
from .weather_service import WeatherService

logger = logging.getLogger("mcp-weather")


def _normalize_aq_variables(
    raw_variables: Sequence[str] | None,
    default_variables: Sequence[str],
) -> list[str]:
    """Validate and normalise the optional ``variables`` argument.

    Accepts any sequence of strings (list, tuple, etc.) — the runtime check
    is ``isinstance(..., (list, tuple))`` rather than ``list`` alone, which
    keeps the type hint (``Sequence[str]``) and runtime behaviour consistent.
    """
    if raw_variables is None:
        return list(default_variables)
    if not isinstance(raw_variables, (list, tuple)):
        raise ValueError("variables must be an array of strings.")
    if len(raw_variables) > len(EXTENDED_AIR_QUALITY_VARIABLES):
        raise ValueError("Too many variables requested.")

    allowed = set(EXTENDED_AIR_QUALITY_VARIABLES)
    normalized: list[str] = []
    for variable in raw_variables:
        if not isinstance(variable, str):
            raise ValueError("variables must contain only strings.")
        if variable not in allowed:
            raise ValueError(f"Unsupported air quality variable: {variable}")
        normalized.append(variable)
    return normalized


class _BaseAirQualityHandler(ToolHandler):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.air_quality_service = AirQualityService()
        self.weather_service = WeatherService()  # for geocoding
        self.formatter = AirQualityFormatter()


class GetAirQualityToolHandler(_BaseAirQualityHandler):
    """Compact, agent-friendly air quality summary."""

    input_model = GetAirQualityInput

    def __init__(self) -> None:
        super().__init__("weather_get_air_quality")

    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description=(
                "Get compact air quality information for a city. "
                "Returns agent-friendly JSON text with current conditions, summary statistics, "
                "and a short hourly sample. Use this for concise analysis."
            ),
            inputSchema=GetAirQualityInput.model_json_schema(),
        )

    async def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        try:
            self.validate_required_args(args, ["city"])
            payload = cast(GetAirQualityInput, self.parse_args(args))
            city = utils.normalize_city_name(payload.city)
            variables = _normalize_aq_variables(payload.variables, DEFAULT_AIR_QUALITY_VARIABLES)

            logger.info("Getting air quality for city=%s variables=%s", city, variables)

            async with ResilientHttpClient(name="air-quality-tools") as http_client:
                latitude, longitude = await self.weather_service.get_coordinates(
                    city, client=http_client
                )
                aq_data = await self.air_quality_service.get_air_quality(
                    latitude, longitude, variables, client=http_client
                )
            current_aq = self.air_quality_service.get_current_air_quality_index(aq_data)
            response_data = {
                "city": city,
                "latitude": latitude,
                "longitude": longitude,
                "current_air_quality": current_aq,
                "full_data": aq_data,
            }
            formatted = self.formatter.format_comprehensive(response_data)
            return [TextContent(type="text", text=formatted)]
        except RuntimeError:
            raise
        except ValueError as exc:
            logger.warning("Invalid request for get_air_quality: %s", exc)
            raise RuntimeError(
                "Invalid air quality request. Check input values and try again."
            ) from exc
        except Exception:
            logger.exception("Unexpected error in get_air_quality")
            raise RuntimeError(
                "Air quality service is temporarily unavailable. Please retry."
            ) from None


class GetAirQualityDetailsToolHandler(_BaseAirQualityHandler):
    """Detailed, raw air quality payload."""

    input_model = GetAirQualityDetailsInput

    def __init__(self) -> None:
        super().__init__("weather_get_air_quality_details")

    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description=(
                "Get detailed air quality data for a city as structured JSON text. "
                "Use this tool when downstream logic needs raw API-like fields in 'full_data'."
            ),
            inputSchema=GetAirQualityDetailsInput.model_json_schema(),
        )

    async def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        try:
            self.validate_required_args(args, ["city"])
            payload = cast(GetAirQualityDetailsInput, self.parse_args(args))
            city = utils.normalize_city_name(payload.city)
            variables = _normalize_aq_variables(payload.variables, EXTENDED_AIR_QUALITY_VARIABLES)

            logger.info("Getting detailed air quality for city=%s", city)

            async with ResilientHttpClient(name="air-quality-tools") as http_client:
                latitude, longitude = await self.weather_service.get_coordinates(
                    city, client=http_client
                )
                aq_data = await self.air_quality_service.get_air_quality(
                    latitude, longitude, variables, client=http_client
                )
            current_aq = self.air_quality_service.get_current_air_quality_index(aq_data)
            response_data = {
                "city": city,
                "latitude": latitude,
                "longitude": longitude,
                "current_air_quality": current_aq,
                "full_data": aq_data,
            }
            return [TextContent(type="text", text=json.dumps(response_data, indent=2))]
        except RuntimeError:
            raise
        except ValueError as exc:
            logger.warning("Invalid request for get_air_quality_details: %s", exc)
            raise RuntimeError(
                "Invalid air quality request. Check input values and try again."
            ) from exc
        except Exception:
            logger.exception("Unexpected error in get_air_quality_details")
            raise RuntimeError(
                "Air quality service is temporarily unavailable. Please retry."
            ) from None
