"""Classify provider-computed US AQI, never hourly mass concentrations."""

from typing import Any

from .series import is_number

SUBINDICES = {
    "pm2_5": "us_aqi_pm2_5",
    "pm10": "us_aqi_pm10",
    "ozone": "us_aqi_ozone",
    "nitrogen_dioxide": "us_aqi_nitrogen_dioxide",
    "sulphur_dioxide": "us_aqi_sulphur_dioxide",
    "carbon_monoxide": "us_aqi_carbon_monoxide",
}
CATEGORIES = (
    (50, "Good"),
    (100, "Moderate"),
    (150, "Unhealthy for Sensitive Groups"),
    (200, "Unhealthy"),
    (300, "Very Unhealthy"),
    (500, "Hazardous"),
)
REFERENCE = "https://open-meteo.com/en/docs/air-quality-api"


def category(value: Any) -> str | None:
    if not is_number(value) or value < 0:
        return None
    return next((label for upper, label in CATEGORIES if value <= upper), "Hazardous")


def index_payload(current: dict[str, Any], variables: list[str]) -> dict[str, Any]:
    pollutants = {}
    for pollutant in variables:
        key = SUBINDICES.get(pollutant)
        value = current.get(key) if key else None
        label = category(value)
        pollutants[pollutant] = {
            "value": value if label else None,
            "category": label,
            "status": "not_supported" if key is None else "available" if label else "unavailable",
            "beyond_scale": bool(label and value is not None and value > 500),
        }
    return {
        "system": "us_aqi",
        "provider": "Open-Meteo",
        "time": current.get("time"),
        "scope": "requested_pollutant_subindices_only",
        "pollutants": pollutants,
        "method": "Provider-computed US AQI subindices using pollutant-specific temporal aggregation; "
        "not classification of hourly concentrations. No independent recalculation.",
        "method_version": "Open-Meteo documentation accessed 2026-11-05; upstream algorithm version not published",
        "references": [REFERENCE, "https://www.airnow.gov/aqi/aqi-basics/"],
        "interpretation_resource": "weather://aqi",
    }


def reference_payload() -> dict[str, Any]:
    bands = [
        {"min_exclusive": lower, "max": upper, "label": label}
        for lower, (upper, label) in zip((None, 50, 100, 150, 200, 300), CATEGORIES, strict=True)
    ]
    return {
        "system": "us_aqi",
        "category_version": "US AQI index categories v1 (2026-11-05)",
        "bands": {key: bands for key in SUBINDICES},
        "index_unit": "dimensionless",
        "concentration_units": "micrograms per cubic metre; aerosol_optical_depth is dimensionless",
        "method": "Subindices supplied by Open-Meteo. PM uses 24-hour, ozone/CO 8-hour "
        "and NO2/SO2 pollutant-specific provider averaging rules; consult the provider reference. "
        "The provider algorithm is not independently audited here.",
        "limits": "First band starts at 0 inclusive. Negative/null/non-finite values are unavailable. "
        "Values above 500 are Hazardous and beyond_scale. No indices for ammonia/dust/AOD. "
        "These are not WHO concentration guidelines or a Brazilian regulatory index.",
        "references": [REFERENCE, "https://www.airnow.gov/aqi/aqi-basics/"],
    }
