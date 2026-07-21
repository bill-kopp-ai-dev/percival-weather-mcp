"""Weather tool handlers for the MCP weather server."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import cast

from mcp.types import EmbeddedResource, ImageContent, TextContent, Tool

from .. import utils
from ..models import (
    GetCurrentWeatherInput,
    GetWeatherByDateRangeInput,
    GetWeatherDetailsInput,
)
from ..presentation import WeatherFormatter
from .toolhandler import ToolHandler
from .weather_service import WeatherService

logger = logging.getLogger("mcp-weather")


class _BaseWeatherHandler(ToolHandler):
    """Shared logic: shared service + shared formatter."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.weather_service = WeatherService()
        self.formatter = WeatherFormatter()


class GetCurrentWeatherToolHandler(_BaseWeatherHandler):
    """Tool handler for the concise current weather snapshot."""

    input_model = GetCurrentWeatherInput

    def __init__(self) -> None:
        super().__init__("weather_get_current")

    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description=(
                "Get a concise, human-readable snapshot of current weather for a city. "
                "Use this tool when you need a short summary (temperature, humidity, wind, "
                "precipitation context, pressure, clouds, UV, visibility), not raw datasets."
            ),
            inputSchema=GetCurrentWeatherInput.model_json_schema(),
        )

    async def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        try:
            self.validate_required_args(args, ["city"])
            payload = cast(GetCurrentWeatherInput, self.parse_args(args))
            city = utils.normalize_city_name(payload.city)
            logger.info("Getting current weather for city=%s", city)
            weather_data = await self.weather_service.get_current_weather(city)
            formatted = self.formatter.format_current(weather_data)
            return [TextContent(type="text", text=formatted)]
        except RuntimeError:
            raise
        except ValueError as exc:
            logger.warning("Invalid request for get_current_weather: %s", exc)
            raise RuntimeError(
                "Invalid weather request. Check input values and try again."
            ) from exc
        except Exception:
            logger.exception("Unexpected error in get_current_weather")
            raise RuntimeError(
                "Weather service is temporarily unavailable. Please retry."
            ) from None


class GetWeatherByDateRangeToolHandler(_BaseWeatherHandler):
    """Tool handler for weather analysis in a date interval."""

    input_model = GetWeatherByDateRangeInput

    def __init__(self) -> None:
        super().__init__("weather_get_by_range")

    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description=(
                "Get weather data for a city between two calendar dates (inclusive). "
                "Returns a compact JSON payload optimized for agent analysis, "
                "including period metadata, summary statistics, and an hourly sample."
            ),
            inputSchema=GetWeatherByDateRangeInput.model_json_schema(),
        )

    async def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        try:
            self.validate_required_args(args, ["city", "start_date", "end_date"])
            payload = cast(GetWeatherByDateRangeInput, self.parse_args(args))
            city = utils.normalize_city_name(payload.city)
            logger.info(
                "Getting weather range for city=%s start_date=%s end_date=%s",
                city,
                payload.start_date,
                payload.end_date,
            )
            weather_data = await self.weather_service.get_weather_by_date_range(
                city, payload.start_date, payload.end_date
            )
            formatted = self.formatter.format_range(weather_data)
            return [TextContent(type="text", text=formatted)]
        except RuntimeError:
            raise
        except ValueError as exc:
            logger.warning("Invalid request for get_weather_by_datetime_range: %s", exc)
            raise RuntimeError(
                "Invalid weather request. Check input values and try again."
            ) from exc
        except Exception:
            logger.exception("Unexpected error in get_weather_by_date_range")
            raise RuntimeError(
                "Weather service is temporarily unavailable. Please retry."
            ) from None


class GetWeatherDetailsToolHandler(_BaseWeatherHandler):
    """Tool handler for detailed, structured-JSON weather data."""

    input_model = GetWeatherDetailsInput

    def __init__(self) -> None:
        super().__init__("weather_get_details")

    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description=(
                "Get detailed structured JSON weather data for a city. "
                "Use this when you need raw fields for downstream processing. "
                "Optionally include a short forecast window."
            ),
            inputSchema=GetWeatherDetailsInput.model_json_schema(),
        )

    async def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        try:
            self.validate_required_args(args, ["city"])
            payload = cast(GetWeatherDetailsInput, self.parse_args(args))
            city = utils.normalize_city_name(payload.city)
            logger.info(
                "Getting detailed weather for city=%s forecast=%s",
                city,
                payload.include_forecast,
            )

            if payload.include_forecast:
                now_utc = datetime.now(timezone.utc)
                today = now_utc.strftime("%Y-%m-%d")
                tomorrow = (now_utc + timedelta(days=1)).strftime("%Y-%m-%d")
                weather_data = await self.weather_service.get_current_weather(
                    city,
                    forecast_days=2,
                    start_date=today,
                    end_date=tomorrow,
                )
            else:
                weather_data = await self.weather_service.get_current_weather(city)

            return [TextContent(type="text", text=json.dumps(weather_data, indent=2))]
        except RuntimeError:
            raise
        except ValueError as exc:
            logger.warning("Invalid request for get_weather_details: %s", exc)
            raise RuntimeError(
                "Invalid weather request. Check input values and try again."
            ) from exc
        except Exception:
            logger.exception("Unexpected error in get_weather_details")
            raise RuntimeError(
                "Weather service is temporarily unavailable. Please retry."
            ) from None
