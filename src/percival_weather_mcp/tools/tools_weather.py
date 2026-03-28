"""
Weather-related tool handlers for the MCP weather server.
This module contains all weather-specific tool implementations.
"""

import json
import logging
from collections.abc import Sequence
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource
from .toolhandler import ToolHandler
from .weather_service import WeatherService
from .. import utils

logger = logging.getLogger("mcp-weather")


class GetCurrentWeatherToolHandler(ToolHandler):
    """
    Tool handler for getting current weather information for a city.
    """
    
    def __init__(self):
        super().__init__("get_current_weather")
        self.weather_service = WeatherService()
    
    def get_tool_description(self) -> Tool:
        """
        Return the MCP contract for a concise current-weather query.
        """
        return Tool(
            name=self.name,
            description=(
                "Get a concise, human-readable snapshot of current weather for a city. "
                "Use this tool when you need a short summary (temperature, humidity, wind, "
                "precipitation context, pressure, clouds, UV, visibility), not raw datasets."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": (
                            "City name in English, optionally with region/country to disambiguate "
                            "(for example: 'Springfield, US' or 'London, UK')."
                        ),
                    }
                },
                "required": ["city"]
            }
        )
    
    async def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        """
        Execute current weather lookup and return one formatted text block.
        """
        try:
            self.validate_required_args(args, ["city"])

            city = utils.normalize_city_name(args["city"])
            logger.info("Getting current weather for city=%s", city)
            
            # Get weather data from service
            weather_data = await self.weather_service.get_current_weather(city)
            
            # Format the response
            formatted_response = self.weather_service.format_current_weather_response(weather_data)
            
            return [
                TextContent(
                    type="text",
                    text=formatted_response
                )
            ]
        except RuntimeError:
            raise
        except ValueError as e:
            logger.warning("Invalid request for get_current_weather: %s", e)
            raise RuntimeError("Invalid weather request. Check input values and try again.") from e
        except Exception:
            logger.exception("Unexpected error in get_current_weather")
            raise RuntimeError("Weather service is temporarily unavailable. Please retry.") from None


class GetWeatherByDateRangeToolHandler(ToolHandler):
    """
    Tool handler for getting weather information for a date range.
    """
    
    def __init__(self):
        super().__init__("get_weather_by_datetime_range")
        self.weather_service = WeatherService()
    
    def get_tool_description(self) -> Tool:
        """
        Return the MCP contract for weather analysis in a date interval.
        """
        return Tool(
            name=self.name,
            description=(
                "Get weather data for a city between two calendar dates (inclusive). "
                "Returns a compact JSON payload optimized for agent analysis, including period metadata, "
                "summary statistics, and an hourly sample."
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
                    "start_date": {
                        "type": "string",
                        "description": (
                            "Start date in ISO 8601 calendar format: YYYY-MM-DD."
                        ),
                    },
                    "end_date": {
                        "type": "string",
                        "description": (
                            "End date in ISO 8601 calendar format: YYYY-MM-DD. "
                            "Must be the same day or after start_date."
                        ),
                    }
                },
                "required": ["city", "start_date", "end_date"]
            }
        )
    
    async def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        """
        Execute date-range weather lookup and return compact JSON text.
        """
        try:
            self.validate_required_args(args, ["city", "start_date", "end_date"])

            city = utils.normalize_city_name(args["city"])
            start_date = args["start_date"]
            end_date = args["end_date"]

            logger.info(
                "Getting weather range for city=%s start_date=%s end_date=%s",
                city,
                start_date,
                end_date,
            )
            
            # Get weather data from service
            weather_data = await self.weather_service.get_weather_by_date_range(
                city, start_date, end_date
            )
            
            # Format the response for analysis
            formatted_response = self.weather_service.format_weather_range_response(weather_data)
            
            return [
                TextContent(
                    type="text",
                    text=formatted_response
                )
            ]
        except RuntimeError:
            raise
        except ValueError as e:
            logger.warning("Invalid request for get_weather_by_datetime_range: %s", e)
            raise RuntimeError("Invalid weather request. Check input values and try again.") from e
        except Exception:
            logger.exception("Unexpected error in get_weather_by_date_range")
            raise RuntimeError("Weather service is temporarily unavailable. Please retry.") from None


class GetWeatherDetailsToolHandler(ToolHandler):
    """
    Tool handler for getting detailed weather information with raw data.
    This tool provides structured JSON output for programmatic use.
    """
    
    def __init__(self):
        super().__init__("get_weather_details")
        self.weather_service = WeatherService()
    
    def get_tool_description(self) -> Tool:
        """
        Return the MCP contract for detailed, raw weather data retrieval.
        """
        return Tool(
            name=self.name,
            description=(
                "Get detailed structured JSON weather data for a city. "
                "Use this when you need raw fields for downstream processing. "
                "Optionally include a short forecast window."
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
                    "include_forecast": {
                        "type": "boolean",
                        "description": (
                            "If true, include the next ~24 hours under the 'forecast' key. "
                            "Defaults to false for smaller responses."
                        ),
                        "default": False
                    }
                },
                "required": ["city"]
            }
        )
    
    async def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        """
        Execute detailed weather lookup and return raw JSON text.
        """
        try:
            self.validate_required_args(args, ["city"])

            city = utils.normalize_city_name(args["city"])
            include_forecast = args.get("include_forecast", False)

            logger.info("Getting detailed weather for city=%s forecast=%s", city, include_forecast)
            
            # Get current weather data
            weather_data = await self.weather_service.get_current_weather(city)
            
            # If forecast is requested, get the next 24 hours
            if include_forecast:
                from datetime import datetime, timedelta
                
                today = datetime.now().strftime("%Y-%m-%d")
                tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
                
                forecast_data = await self.weather_service.get_weather_by_date_range(
                    city, today, tomorrow
                )
                weather_data["forecast"] = forecast_data["weather_data"]
            
            return [
                TextContent(
                    type="text",
                    text=json.dumps(weather_data, indent=2)
                )
            ]
        except RuntimeError:
            raise
        except ValueError as e:
            logger.warning("Invalid request for get_weather_details: %s", e)
            raise RuntimeError("Invalid weather request. Check input values and try again.") from e
        except Exception:
            logger.exception("Unexpected error in get_weather_details")
            raise RuntimeError("Weather service is temporarily unavailable. Please retry.") from None
