"""Formatting helpers for air-quality responses."""

from __future__ import annotations

from typing import Any

from .. import utils
from ..series import is_number


class AirQualityFormatter:
    """Concentrations are not AQI and carry no concentration-based advice."""

    def format_legacy(
        self, city: str, latitude: float, longitude: float, aq_data: dict[str, Any]
    ) -> str:
        """Compatibility view of concentrations only; indices use weather://aqi."""
        parts = [
            f"Air quality in {utils.safe_inline_text(city)} (lat: {latitude:.2f}, lon: {longitude:.2f}):"
        ]
        for key, label in (
            ("pm2_5", "PM2.5"),
            ("pm10", "PM10"),
            ("ozone", "Ozone (O3)"),
            ("nitrogen_dioxide", "Nitrogen Dioxide (NO2)"),
            ("carbon_monoxide", "Carbon Monoxide (CO)"),
            ("sulphur_dioxide", "Sulfur Dioxide (SO2)"),
            ("ammonia", "Ammonia (NH3)"),
            ("dust", "Dust"),
            ("aerosol_optical_depth", "Aerosol Optical Depth"),
        ):
            if key not in aq_data:
                continue
            value = aq_data[key]
            unit = "dimensionless" if key == "aerosol_optical_depth" else "μg/m³"
            parts.append(f"{label}: {value if is_number(value) else 'unavailable'} {unit}")
        parts.append(
            "Concentrations are not AQI. See weather://aqi for provider-computed index interpretation."
        )
        return "\n".join(parts)

    @staticmethod
    def format_comprehensive(response_data: dict[str, Any]) -> str:
        return utils.format_air_quality_data(response_data)
