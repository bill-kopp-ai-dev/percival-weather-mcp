"""Formatting helpers for air-quality responses."""

from __future__ import annotations

from typing import Any

from .. import utils


class AirQualityFormatter:
    """Stateless helpers that turn raw air-quality payloads into readable text."""

    @staticmethod
    def _pm25_level(pm25: float) -> str:
        if pm25 <= 12:
            return "Good"
        if pm25 <= 35:
            return "Moderate"
        if pm25 <= 55:
            return "Unhealthy for Sensitive Groups"
        if pm25 <= 150:
            return "Unhealthy"
        if pm25 <= 250:
            return "Very Unhealthy"
        return "Hazardous"

    @staticmethod
    def _pm10_level(pm10: float) -> str:
        if pm10 <= 54:
            return "Good"
        if pm10 <= 154:
            return "Moderate"
        if pm10 <= 254:
            return "Unhealthy for Sensitive Groups"
        if pm10 <= 354:
            return "Unhealthy"
        if pm10 <= 424:
            return "Very Unhealthy"
        return "Hazardous"

    @staticmethod
    def _health_advice(pm25: float) -> str:
        if pm25 <= 12:
            return "Air quality is good. Safe for outdoor activities."
        if pm25 <= 35:
            return (
                "Air quality is acceptable. Sensitive individuals should consider "
                "reducing prolonged outdoor exertion."
            )
        if pm25 <= 55:
            return (
                "Sensitive groups (children, elderly, people with respiratory conditions) "
                "should limit outdoor activities."
            )
        if pm25 <= 150:
            return (
                "Everyone should reduce outdoor activities. "
                "Sensitive groups should avoid outdoor activities."
            )
        if pm25 <= 250:
            return (
                "Everyone should avoid outdoor activities. Sensitive groups should remain indoors."
            )
        return "Health alert: Everyone should avoid all outdoor activities and remain indoors."

    def format_legacy(
        self, city: str, latitude: float, longitude: float, aq_data: dict[str, Any]
    ) -> str:
        """Render a human-readable, single-line-per-pollutant view."""
        safe_city = utils.safe_inline_text(city)
        parts = [f"Air quality in {safe_city} (lat: {latitude:.2f}, lon: {longitude:.2f}):"]

        for key, label, level_fn in (
            ("pm2_5", "PM2.5", self._pm25_level),
            ("pm10", "PM10", self._pm10_level),
            ("ozone", "Ozone (O3)", None),
            ("nitrogen_dioxide", "Nitrogen Dioxide (NO2)", None),
            ("carbon_monoxide", "Carbon Monoxide (CO)", None),
            ("sulphur_dioxide", "Sulfur Dioxide (SO2)", None),
            ("ammonia", "Ammonia (NH3)", None),
            ("dust", "Dust", None),
            ("aerosol_optical_depth", "Aerosol Optical Depth", None),
        ):
            if key not in aq_data:
                continue
            value = aq_data[key]
            if key == "aerosol_optical_depth":
                parts.append(f"{label}: {value:.3f}")
            else:
                line = f"{label}: {value:.1f} μg/m³"
                if level_fn is not None:
                    line += f" ({level_fn(value)})"
                parts.append(line)

        if "pm2_5" in aq_data:
            parts.append("")
            parts.append(f"Health Advice: {self._health_advice(aq_data['pm2_5'])}")

        return "\n".join(parts)

    @staticmethod
    def format_comprehensive(response_data: dict[str, Any]) -> str:
        """Render the structured, agent-friendly JSON payload used by tool handlers."""
        return utils.format_air_quality_data(response_data)
