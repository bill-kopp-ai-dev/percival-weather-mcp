"""Air quality tool handlers for the MCP weather server."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import cast

from mcp.types import EmbeddedResource, ImageContent, TextContent, Tool

from .. import series, utils
from ..air_quality_index import index_payload
from ..errors import InvalidRequestError, UpstreamError, WeatherMCPError
from ..http_client import ResilientHttpClient
from ..models import (
    DEFAULT_AIR_QUALITY_VARIABLES,
    EXTENDED_AIR_QUALITY_VARIABLES,
    GetAirQualityDetailsInput,
    GetAirQualityInput,
)
from ..output_models import AirQualityDetails, serialize
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
        raise InvalidRequestError("variables must be an array of strings.")
    if not raw_variables:
        raise InvalidRequestError(
            "variables must contain at least 1 pollutant; omit it for defaults."
        )
    if len(raw_variables) > len(EXTENDED_AIR_QUALITY_VARIABLES):
        raise InvalidRequestError("variables must contain at most 9 entries.")

    allowed = set(EXTENDED_AIR_QUALITY_VARIABLES)
    normalized: list[str] = []
    for variable in raw_variables:
        if not isinstance(variable, str):
            raise InvalidRequestError("variables must contain only strings.")
        if variable not in allowed:
            raise InvalidRequestError(
                "variables contains an unsupported pollutant; consult the input schema enum."
            )
        if variable not in normalized:
            normalized.append(variable)
    return normalized


class _BaseAirQualityHandler(ToolHandler):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.air_quality_service = AirQualityService()
        self.weather_service = WeatherService()  # for geocoding
        self.formatter = AirQualityFormatter()

    async def _query(self, city: str, variables: list[str]) -> dict:
        reference = series.utc_now()
        async with ResilientHttpClient(name="air-quality-tools") as http_client:
            resolved = await self.weather_service.resolve_location(city, client=http_client)
            latitude, longitude = resolved.selected.latitude, resolved.selected.longitude
            aq_data = await self.air_quality_service.get_air_quality(
                latitude, longitude, variables, client=http_client
            )
        current = self.air_quality_service.get_current_air_quality_index(
            aq_data, reference=reference
        )
        return {
            "city": city,
            "latitude": latitude,
            "longitude": longitude,
            **resolved.context(),
            "source": series.provenance("air-quality"),
            "selection_method": "nearest_hour",
            "reference_time": reference.isoformat(),
            "timezone": "UTC",
            "current_air_quality": current,
            "full_data": aq_data,
            "air_quality_index": index_payload(current, variables),
            "coverage": series.series_metadata(
                aq_data.get("hourly") or {}, variables, reference=reference, expected_points=120
            ),
        }


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
                " Includes selected location, UTC model timestamps, valid/missing coverage and provider-computed US AQI subindices."
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

            response_data = await self._query(city, variables)
            formatted = self.formatter.format_comprehensive(response_data)
            return [TextContent(type="text", text=formatted)]
        except WeatherMCPError:
            # Taxonomy errors already carry the agent-facing message and
            # the true cause (upstream failure, empty result, local validation).
            raise
        except ValueError as exc:
            logger.warning("Invalid request for get_air_quality: %s", exc)
            raise InvalidRequestError(
                "Invalid air quality request. Check input values and try again."
            ) from exc
        except Exception:
            logger.exception("Unexpected error in get_air_quality")
            raise UpstreamError(
                "Air quality service is temporarily unavailable. Please retry.",
                service="air-quality",
                reason="internal_error",
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
                " Preserves all upstream arrays; adds location, temporal coverage and provider-computed US AQI (weather://aqi)."
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

            response_data = await self._query(city, variables)
            return [TextContent(type="text", text=serialize(AirQualityDetails, response_data))]
        except WeatherMCPError:
            # Taxonomy errors already carry the agent-facing message and
            # the true cause (upstream failure, empty result, local validation).
            raise
        except ValueError as exc:
            logger.warning("Invalid request for get_air_quality_details: %s", exc)
            raise InvalidRequestError(
                "Invalid air quality request. Check input values and try again."
            ) from exc
        except Exception:
            logger.exception("Unexpected error in get_air_quality_details")
            raise UpstreamError(
                "Air quality service is temporarily unavailable. Please retry.",
                service="air-quality",
                reason="internal_error",
            ) from None
