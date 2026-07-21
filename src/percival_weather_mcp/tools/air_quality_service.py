"""Air quality service for handling air-quality API interactions."""

from __future__ import annotations

import logging
from typing import Any

from .. import utils
from ..http_client import ResilientHttpClient

logger = logging.getLogger("mcp-weather")


class AirQualityService:
    """Service class for air quality API interactions."""

    BASE_AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

    async def get_air_quality(
        self,
        latitude: float,
        longitude: float,
        hourly_vars: list[str] | None = None,
        client: ResilientHttpClient | None = None,
    ) -> dict[str, Any]:
        """Fetch air-quality data for the given coordinates."""
        if hourly_vars is None:
            hourly_vars = ["pm10", "pm2_5", "ozone", "nitrogen_dioxide", "carbon_monoxide"]

        hourly_str = ",".join(hourly_vars)
        logger.info(
            "Fetching air quality data for lat=%s lon=%s variables=%s",
            latitude,
            longitude,
            hourly_vars,
        )

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": hourly_str,
            "timezone": "GMT",
        }

        own_client = client is None
        target = client or ResilientHttpClient(name="air-quality")
        if own_client:
            async with target as opened:
                return await opened.get_json(self.BASE_AIR_QUALITY_URL, params=params)
        return await target.get_json(self.BASE_AIR_QUALITY_URL, params=params)

    def get_current_air_quality_index(self, aq_data: dict[str, Any]) -> dict[str, Any]:
        """Extract the current hour slice from the air-quality hourly series."""
        hourly = aq_data.get("hourly") or {}
        times = hourly.get("time") or []
        if not times:
            return {}
        current_index = utils.get_closest_utc_index(times)
        result: dict[str, Any] = {"time": times[current_index]}
        for key, values in hourly.items():
            if key == "time":
                continue
            if isinstance(values, list) and current_index < len(values):
                result[key] = values[current_index]
        return result

    def format_response(
        self,
        city: str,
        latitude: float,
        longitude: float,
        aq_data: dict[str, Any],
    ) -> str:
        """Render a legacy, single-line-per-pollutant view (legacy compatibility)."""
        from ..presentation import AirQualityFormatter

        formatter = AirQualityFormatter()
        return formatter.format_legacy(city, latitude, longitude, aq_data)

    def format_air_quality_comprehensive(self, response_data: dict[str, Any]) -> str:
        """Render the structured, agent-friendly JSON payload."""
        from ..presentation import AirQualityFormatter

        return AirQualityFormatter.format_comprehensive(response_data)
