"""Air quality service for handling air-quality API interactions."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from .. import series, utils
from ..air_quality_index import SUBINDICES
from ..errors import InvalidRequestError, NoDataError
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

        if not hourly_vars:
            raise InvalidRequestError("variables must contain at least 1 pollutant.")
        hourly_vars = list(dict.fromkeys(hourly_vars))
        hourly_str = ",".join(hourly_vars + [SUBINDICES[v] for v in hourly_vars if v in SUBINDICES])
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
            "forecast_days": 5,
        }

        own_client = client is None
        target = client or ResilientHttpClient(name="air-quality")
        if own_client:
            async with target as opened:
                data = await opened.get_json(self.BASE_AIR_QUALITY_URL, params=params)
        else:
            data = await target.get_json(self.BASE_AIR_QUALITY_URL, params=params)

        hourly = data.get("hourly") or {}
        times = (hourly or {}).get("time") or []
        if not times:
            # Successful answer without usable series: neither an upstream
            # failure nor a local validation failure.
            raise NoDataError(
                "Open-Meteo air quality returned an empty hourly series. "
                "No air-quality data is available for the requested coordinates."
            )
        if not any(
            series.is_number(series.value_at(hourly.get(v), i))
            for v in hourly_vars
            for i in range(len(times))
        ):
            raise NoDataError(
                "Open-Meteo returned no valid numeric data for the requested pollutants."
            )
        return data

    def get_current_air_quality_index(
        self, aq_data: dict[str, Any], *, reference: datetime | None = None
    ) -> dict[str, Any]:
        """Extract the current hour slice from the air-quality hourly series."""
        hourly = aq_data.get("hourly") or {}
        times = hourly.get("time") or []
        if not times:
            return {}
        current_index = utils.get_closest_utc_index(times, reference=reference)
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
