"""Weather service for handling all weather API interactions.

This separates business logic from tool handlers and routes every outbound HTTP
call through :mod:`percival_weather_mcp.http_client` so that retries, circuit
breaking and concurrency limits are consistent across the codebase.
"""

from __future__ import annotations

import logging
from time import monotonic
from typing import Any

from .. import utils
from ..config import get_settings
from ..http_client import ResilientHttpClient, get_geo_breaker

logger = logging.getLogger("mcp-weather")


class WeatherService:
    """Service class for weather-related API interactions."""

    BASE_GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
    BASE_WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

    HOURLY_VARIABLES = (
        "temperature_2m,relative_humidity_2m,dew_point_2m,weather_code,"
        "wind_speed_10m,wind_direction_10m,wind_gusts_10m,"
        "precipitation,rain,snowfall,precipitation_probability,"
        "pressure_msl,cloud_cover,uv_index,apparent_temperature,visibility"
    )

    def __init__(self) -> None:
        self._coordinates_cache: dict[str, tuple[float, float, float]] = {}
        self._settings = get_settings()

    # ------------------------------------------------------------------
    # Geocoding cache
    # ------------------------------------------------------------------

    def _cache_key(self, city: str) -> str:
        return city.strip().lower()

    def _get_cached_coordinates(self, city: str) -> tuple[float, float] | None:
        key = self._cache_key(city)
        cached = self._coordinates_cache.get(key)
        if not cached:
            return None
        latitude, longitude, expires_at = cached
        if monotonic() >= expires_at:
            self._coordinates_cache.pop(key, None)
            return None
        return latitude, longitude

    def _set_cached_coordinates(self, city: str, latitude: float, longitude: float) -> None:
        key = self._cache_key(city)
        cache = self._coordinates_cache
        max_size = self._settings.geo_cache_max_size
        ttl = self._settings.geo_cache_ttl_seconds
        if key not in cache and len(cache) >= max_size:
            oldest_key = min(cache, key=lambda candidate: cache[candidate][2])
            cache.pop(oldest_key, None)
        cache[key] = (latitude, longitude, monotonic() + ttl)

    async def get_coordinates(
        self,
        city: str,
        client: ResilientHttpClient | None = None,
    ) -> tuple[float, float]:
        """Fetch the (latitude, longitude) for ``city`` via the geocoding API."""
        city = utils.normalize_city_name(city)
        cached = self._get_cached_coordinates(city)
        if cached is not None:
            return cached

        breaker = get_geo_breaker()
        own_client = client is None
        client = client or ResilientHttpClient(name="geocoding")
        try:
            if own_client:
                async with client as opened:
                    data = await opened.get_json(
                        self.BASE_GEO_URL,
                        params={
                            "name": city,
                            "count": 1,
                            "language": "en",
                            "format": "json",
                        },
                        breaker=breaker,
                    )
            else:
                data = await client.get_json(
                    self.BASE_GEO_URL,
                    params={
                        "name": city,
                        "count": 1,
                        "language": "en",
                        "format": "json",
                    },
                    breaker=breaker,
                )
        except Exception:
            raise

        results = data.get("results") if isinstance(data, dict) else None
        if not results:
            raise ValueError(f"No coordinates found for city: {city}")

        result = results[0]
        latitude = float(result["latitude"])
        longitude = float(result["longitude"])
        self._set_cached_coordinates(city, latitude, longitude)
        return latitude, longitude

    # ------------------------------------------------------------------
    # Date range validation
    # ------------------------------------------------------------------

    def _validate_date_range(self, start_date: str, end_date: str) -> tuple[str, str]:
        from datetime import datetime

        try:
            parsed_start = datetime.strptime(start_date, "%Y-%m-%d").date()
            parsed_end = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError("Dates must use YYYY-MM-DD format.") from exc

        if parsed_end < parsed_start:
            raise ValueError("end_date must be on or after start_date.")

        requested_days = (parsed_end - parsed_start).days + 1
        if requested_days > self._settings.max_date_range_days:
            raise ValueError(
                f"Date range exceeds {self._settings.max_date_range_days} days. "
                "Please use a shorter interval."
            )

        return parsed_start.isoformat(), parsed_end.isoformat()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_current_weather(
        self,
        city: str,
        *,
        forecast_days: int = 1,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """Get weather information for a city.

        When ``forecast_days`` > 1, ``start_date`` and ``end_date`` should be set
        to constrain the result; this is used by the detailed tool to fetch
        current + forecast data with a single HTTP call.
        """
        from datetime import datetime, timedelta, timezone

        city = utils.normalize_city_name(city)
        async with ResilientHttpClient(name="weather") as http_client:
            latitude, longitude = await self.get_coordinates(city, client=http_client)
            params: dict[str, Any] = {
                "latitude": latitude,
                "longitude": longitude,
                "hourly": self.HOURLY_VARIABLES,
                "timezone": "GMT",
            }
            if start_date and end_date:
                params["start_date"] = start_date
                params["end_date"] = end_date
            else:
                params["forecast_days"] = forecast_days

            logger.info(
                "Fetching weather for city=%s start=%s end=%s days=%s",
                city,
                start_date,
                end_date,
                forecast_days,
            )
            data = await http_client.get_json(self.BASE_WEATHER_URL, params=params)

        hourly = data.get("hourly") or {}
        times = hourly.get("time") or []
        if not times:
            raise ValueError("Weather API returned an empty hourly series.")

        current_index = utils.get_closest_utc_index(times)
        now_utc = datetime.now(timezone.utc)
        forecast_window_end = now_utc + timedelta(hours=24)
        forecast_indices: list[int] = []
        if forecast_days > 1 or (start_date and end_date):
            for i, ts in enumerate(times):
                try:
                    moment = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if moment.tzinfo is None:
                    moment = moment.replace(tzinfo=timezone.utc)
                if now_utc <= moment <= forecast_window_end:
                    forecast_indices.append(i)

        def _value(key: str, index: int) -> Any:
            values = hourly.get(key) or []
            if index >= len(values):
                return None
            return values[index]

        current_weather: dict[str, Any] = {
            "city": city,
            "latitude": latitude,
            "longitude": longitude,
            "time": _value("time", current_index),
            "temperature_c": _value("temperature_2m", current_index),
            "relative_humidity_percent": _value("relative_humidity_2m", current_index),
            "dew_point_c": _value("dew_point_2m", current_index),
            "weather_code": _value("weather_code", current_index),
            "weather_description": utils.weather_descriptions.get(
                _value("weather_code", current_index) or -1,
                "Unknown weather condition",
            ),
            "wind_speed_kmh": _value("wind_speed_10m", current_index),
            "wind_direction_degrees": _value("wind_direction_10m", current_index),
            "wind_gusts_kmh": _value("wind_gusts_10m", current_index),
            "precipitation_mm": _value("precipitation", current_index),
            "rain_mm": _value("rain", current_index),
            "snowfall_cm": _value("snowfall", current_index),
            "precipitation_probability_percent": _value(
                "precipitation_probability", current_index
            ),
            "pressure_hpa": _value("pressure_msl", current_index),
            "cloud_cover_percent": _value("cloud_cover", current_index),
            "uv_index": _value("uv_index", current_index),
            "apparent_temperature_c": _value("apparent_temperature", current_index),
            "visibility_m": _value("visibility", current_index),
        }

        if forecast_indices:
            forecast = []
            for idx in forecast_indices:
                forecast.append(
                    {
                        "time": _value("time", idx),
                        "temperature_c": _value("temperature_2m", idx),
                        "humidity_percent": _value("relative_humidity_2m", idx),
                        "dew_point_c": _value("dew_point_2m", idx),
                        "weather_code": _value("weather_code", idx),
                        "weather_description": utils.weather_descriptions.get(
                            _value("weather_code", idx) or -1,
                            "Unknown weather condition",
                        ),
                        "wind_speed_kmh": _value("wind_speed_10m", idx),
                        "wind_direction_degrees": _value("wind_direction_10m", idx),
                        "wind_gusts_kmh": _value("wind_gusts_10m", idx),
                        "precipitation_mm": _value("precipitation", idx),
                        "rain_mm": _value("rain", idx),
                        "snowfall_cm": _value("snowfall", idx),
                        "precipitation_probability_percent": _value(
                            "precipitation_probability", idx
                        ),
                        "pressure_hpa": _value("pressure_msl", idx),
                        "cloud_cover_percent": _value("cloud_cover", idx),
                        "uv_index": _value("uv_index", idx),
                        "apparent_temperature_c": _value("apparent_temperature", idx),
                        "visibility_m": _value("visibility", idx),
                    }
                )
            current_weather["forecast"] = forecast

        return current_weather

    async def get_weather_by_date_range(
        self,
        city: str,
        start_date: str,
        end_date: str,
    ) -> dict[str, Any]:
        """Get hourly weather information between two calendar dates (inclusive)."""
        city = utils.normalize_city_name(city)
        start_date, end_date = self._validate_date_range(start_date, end_date)

        async with ResilientHttpClient(name="weather") as http_client:
            latitude, longitude = await self.get_coordinates(city, client=http_client)
            logger.info(
                "Fetching weather history for city=%s start_date=%s end_date=%s",
                city,
                start_date,
                end_date,
            )
            data = await http_client.get_json(
                self.BASE_WEATHER_URL,
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "hourly": self.HOURLY_VARIABLES,
                    "timezone": "GMT",
                    "start_date": start_date,
                    "end_date": end_date,
                },
            )

        hourly = data.get("hourly") or {}
        times = hourly.get("time") or []
        weather_data: list[dict[str, Any]] = []
        for i, ts in enumerate(times):
            weather_data.append(
                {
                    "time": ts,
                    "temperature_c": (hourly.get("temperature_2m") or [None])[i]
                    if i < len(hourly.get("temperature_2m") or [])
                    else None,
                    "humidity_percent": (hourly.get("relative_humidity_2m") or [None])[i]
                    if i < len(hourly.get("relative_humidity_2m") or [])
                    else None,
                    "dew_point_c": (hourly.get("dew_point_2m") or [None])[i]
                    if i < len(hourly.get("dew_point_2m") or [])
                    else None,
                    "weather_code": (hourly.get("weather_code") or [None])[i]
                    if i < len(hourly.get("weather_code") or [])
                    else None,
                    "weather_description": utils.weather_descriptions.get(
                        (hourly.get("weather_code") or [None])[i]
                        if i < len(hourly.get("weather_code") or [])
                        else -1,
                        "Unknown weather condition",
                    ),
                    "wind_speed_kmh": (hourly.get("wind_speed_10m") or [None])[i]
                    if i < len(hourly.get("wind_speed_10m") or [])
                    else None,
                    "wind_direction_degrees": (hourly.get("wind_direction_10m") or [None])[i]
                    if i < len(hourly.get("wind_direction_10m") or [])
                    else None,
                    "wind_gusts_kmh": (hourly.get("wind_gusts_10m") or [None])[i]
                    if i < len(hourly.get("wind_gusts_10m") or [])
                    else None,
                    "precipitation_mm": (hourly.get("precipitation") or [None])[i]
                    if i < len(hourly.get("precipitation") or [])
                    else None,
                    "rain_mm": (hourly.get("rain") or [None])[i]
                    if i < len(hourly.get("rain") or [])
                    else None,
                    "snowfall_cm": (hourly.get("snowfall") or [None])[i]
                    if i < len(hourly.get("snowfall") or [])
                    else None,
                    "precipitation_probability_percent": (
                        hourly.get("precipitation_probability") or [None]
                    )[i]
                    if i < len(hourly.get("precipitation_probability") or [])
                    else None,
                    "pressure_hpa": (hourly.get("pressure_msl") or [None])[i]
                    if i < len(hourly.get("pressure_msl") or [])
                    else None,
                    "cloud_cover_percent": (hourly.get("cloud_cover") or [None])[i]
                    if i < len(hourly.get("cloud_cover") or [])
                    else None,
                    "uv_index": (hourly.get("uv_index") or [None])[i]
                    if i < len(hourly.get("uv_index") or [])
                    else None,
                    "apparent_temperature_c": (
                        hourly.get("apparent_temperature") or [None]
                    )[i]
                    if i < len(hourly.get("apparent_temperature") or [])
                    else None,
                    "visibility_m": (hourly.get("visibility") or [None])[i]
                    if i < len(hourly.get("visibility") or [])
                    else None,
                }
            )

        return {
            "city": city,
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start_date,
            "end_date": end_date,
            "weather_data": weather_data,
        }
