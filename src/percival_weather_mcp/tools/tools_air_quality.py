"""
Air Quality tool handlers for the MCP weather server.
This module contains air quality-specific tool implementations.
"""

import json
import logging
from collections.abc import Sequence
import httpx
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource
from .toolhandler import ToolHandler
from .air_quality_service import AirQualityService
from .weather_service import WeatherService
from .. import utils

logger = logging.getLogger("mcp-weather")

ALLOWED_AIR_QUALITY_VARIABLES = {
    "pm10",
    "pm2_5",
    "carbon_monoxide",
    "nitrogen_dioxide",
    "ozone",
    "sulphur_dioxide",
    "ammonia",
    "dust",
    "aerosol_optical_depth",
}


def _normalize_aq_variables(raw_variables: list[str] | None, default_variables: list[str]) -> list[str]:
    if raw_variables is None:
        return default_variables
    if not isinstance(raw_variables, list):
        raise ValueError("variables must be an array of strings.")
    if len(raw_variables) > len(ALLOWED_AIR_QUALITY_VARIABLES):
        raise ValueError("Too many variables requested.")

    normalized: list[str] = []
    for variable in raw_variables:
        if not isinstance(variable, str):
            raise ValueError("variables must contain only strings.")
        if variable not in ALLOWED_AIR_QUALITY_VARIABLES:
            raise ValueError(f"Unsupported air quality variable: {variable}")
        normalized.append(variable)
    return normalized


class GetAirQualityToolHandler(ToolHandler):
    """
    Tool handler for getting air quality information for a city.
    Provides PM2.5, PM10, ozone, and other pollutant data.
    """

    def __init__(self):
        super().__init__("weather_get_air_quality")
        self.air_quality_service = AirQualityService()
        self.weather_service = WeatherService()  # For geocoding

    def get_tool_description(self) -> Tool:
        """
        Return the MCP contract for compact air quality analysis.
        """
        return Tool(
            name=self.name,
            description=(
                "Get compact air quality information for a city. "
                "Returns agent-friendly JSON text with current conditions, summary statistics, "
                "and a short hourly sample. Use this for concise analysis."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": (
                            "City name in English, optionally with region/country to disambiguate."
                        ),
                    },
                    "variables": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "pm10",
                                "pm2_5",
                                "carbon_monoxide",
                                "nitrogen_dioxide",
                                "ozone",
                                "sulphur_dioxide",
                                "ammonia",
                                "dust",
                                "aerosol_optical_depth"
                            ]
                        },
                        "description": (
                            "Optional subset of pollutant variables. "
                            "If omitted, defaults to: pm10, pm2_5, ozone, nitrogen_dioxide, carbon_monoxide."
                        ),
                    }
                },
                "required": ["city"]
            }
        )

    async def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        """
        Execute compact air quality lookup and return JSON text.
        """
        try:
            self.validate_required_args(args, ["city"])

            city = utils.normalize_city_name(args["city"])
            variables = _normalize_aq_variables(
                args.get("variables"),
                ["pm10", "pm2_5", "ozone", "nitrogen_dioxide", "carbon_monoxide"],
            )

            logger.info("Getting air quality for city=%s variables=%s", city, variables)

            async with httpx.AsyncClient(timeout=self.weather_service.HTTP_TIMEOUT_SECONDS) as shared_client:
                # Reuse a single HTTP client for geocoding + air quality request in this call.
                latitude, longitude = await self.weather_service.get_coordinates(
                    city,
                    client=shared_client,
                )
                aq_data = await self.air_quality_service.get_air_quality(
                    latitude,
                    longitude,
                    variables,
                    client=shared_client,
                )

            # Get current air quality values
            current_aq = self.air_quality_service.get_current_air_quality_index(aq_data)

            # Build comprehensive response data for AI comprehension
            response_data = {
                "city": city,
                "latitude": latitude,
                "longitude": longitude,
                "current_air_quality": current_aq,
                "full_data": aq_data
            }

            # Format the response with comprehensive field descriptions
            formatted_response = self.air_quality_service.format_air_quality_comprehensive(
                response_data
            )

            return [
                TextContent(
                    type="text",
                    text=formatted_response
                )
            ]
        except RuntimeError:
            raise
        except ValueError as e:
            logger.warning("Invalid request for get_air_quality: %s", e)
            raise RuntimeError("Invalid air quality request. Check input values and try again.") from e
        except Exception:
            logger.exception("Unexpected error in get_air_quality")
            raise RuntimeError("Air quality service is temporarily unavailable. Please retry.") from None


class GetAirQualityDetailsToolHandler(ToolHandler):
    """
    Tool handler for getting detailed air quality information with raw data.
    This tool provides structured JSON output for programmatic use.
    """

    def __init__(self):
        super().__init__("weather_get_air_quality_details")
        self.air_quality_service = AirQualityService()
        self.weather_service = WeatherService()  # For geocoding

    def get_tool_description(self) -> Tool:
        """
        Return the MCP contract for detailed/raw air quality retrieval.
        """
        return Tool(
            name=self.name,
            description=(
                "Get detailed air quality data for a city as structured JSON text. "
                "Use this tool when downstream logic needs raw API-like fields in 'full_data'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": (
                            "City name in English, optionally with region/country to disambiguate."
                        ),
                    },
                    "variables": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "pm10",
                                "pm2_5",
                                "carbon_monoxide",
                                "nitrogen_dioxide",
                                "ozone",
                                "sulphur_dioxide",
                                "ammonia",
                                "dust",
                                "aerosol_optical_depth"
                            ]
                        },
                        "description": (
                            "Optional pollutant list. If omitted, uses an extended default set "
                            "covering major pollutants and particulates."
                        ),
                    }
                },
                "required": ["city"]
            }
        )

    async def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        """
        Execute detailed air quality lookup and return raw JSON text.
        """
        try:
            self.validate_required_args(args, ["city"])

            city = utils.normalize_city_name(args["city"])
            variables = _normalize_aq_variables(
                args.get("variables"),
                [
                    "pm10",
                    "pm2_5",
                    "ozone",
                    "nitrogen_dioxide",
                    "carbon_monoxide",
                    "sulphur_dioxide",
                    "ammonia",
                    "dust",
                    "aerosol_optical_depth",
                ],
            )

            logger.info("Getting detailed air quality for city=%s", city)

            async with httpx.AsyncClient(timeout=self.weather_service.HTTP_TIMEOUT_SECONDS) as shared_client:
                # Reuse a single HTTP client for geocoding + air quality request in this call.
                latitude, longitude = await self.weather_service.get_coordinates(
                    city,
                    client=shared_client,
                )
                aq_data = await self.air_quality_service.get_air_quality(
                    latitude,
                    longitude,
                    variables,
                    client=shared_client,
                )

            # Get current air quality values
            current_aq = self.air_quality_service.get_current_air_quality_index(aq_data)

            # Build response with metadata
            response_data = {
                "city": city,
                "latitude": latitude,
                "longitude": longitude,
                "current_air_quality": current_aq,
                "full_data": aq_data
            }

            return [
                TextContent(
                    type="text",
                    text=json.dumps(response_data, indent=2)
                )
            ]
        except RuntimeError:
            raise
        except ValueError as e:
            logger.warning("Invalid request for get_air_quality_details: %s", e)
            raise RuntimeError("Invalid air quality request. Check input values and try again.") from e
        except Exception:
            logger.exception("Unexpected error in get_air_quality_details")
            raise RuntimeError("Air quality service is temporarily unavailable. Please retry.") from None
