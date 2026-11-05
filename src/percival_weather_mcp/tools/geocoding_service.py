"""Bounded geocoding with explicit identity and qualifier-preserving fallback."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from ..errors import NoDataError
from ..http_client import ResilientHttpClient, get_geo_breaker, get_geocoding_cache
from ..utils import normalize_city_name

# Product alias set v1 (2026-11-05), ISO 3166-1 alpha-2 country codes.
# Deliberately bounded: unknown translations/region abbreviations are not guessed.
COUNTRY_ALIASES = {
    "uk": "GB",
    "gb": "GB",
    "united kingdom": "GB",
    "reino unido": "GB",
    "br": "BR",
    "brazil": "BR",
    "brasil": "BR",
    "fr": "FR",
    "france": "FR",
    "frança": "FR",
    "pt": "PT",
    "portugal": "PT",
    "us": "US",
    "usa": "US",
    "united states": "US",
    "estados unidos": "US",
    "de": "DE",
    "germany": "DE",
    "alemanha": "DE",
    "jp": "JP",
    "japan": "JP",
    "japão": "JP",
    "ca": "CA",
    "canada": "CA",
    "canadá": "CA",
    "au": "AU",
    "australia": "AU",
    "es": "ES",
    "spain": "ES",
    "espanha": "ES",
    "it": "IT",
    "italy": "IT",
    "italia": "IT",
    "itália": "IT",
    "cn": "CN",
    "china": "CN",
    "in": "IN",
    "india": "IN",
    "índia": "IN",
    "ar": "AR",
    "argentina": "AR",
}
REGION_ALIASES = {
    "il": "illinois",
    "dc": "district of columbia",
    "d.c.": "district of columbia",
    "ny": "new york",
    "ca": "california",
}


@dataclass(frozen=True)
class Location:
    latitude: float
    longitude: float
    name: str | None = None
    country: str | None = None
    country_code: str | None = None
    admin1: str | None = None
    timezone: str | None = None
    feature_code: str | None = None
    id: int | None = None


@dataclass(frozen=True)
class ResolvedLocation:
    selected: Location
    candidates: tuple[Location, ...]
    query: str
    country_filter: str | None = None

    def context(self) -> dict[str, Any]:
        return {
            "location": asdict(self.selected),
            "resolution": {
                "query": self.query,
                "language": "en",
                "country_filter": self.country_filter,
                "selection": "first_provider_candidate",
                "ambiguous": len(self.candidates) > 1,
                "candidate_count": len(self.candidates),
                "search_limit": 10,
                "uniqueness_guaranteed": False,
                "alternatives": [asdict(c) for c in self.candidates[1:4]],
            },
        }


class GeocodingService:
    BASE_URL = "https://geocoding-api.open-meteo.com/v1/search"

    async def resolve(
        self, city: str, client: ResilientHttpClient | None = None
    ) -> ResolvedLocation:
        city = normalize_city_name(city)
        cache = get_geocoding_cache()
        cached = cache.get_location(city)
        if cached is not None:
            return cached
        if client is None:
            async with ResilientHttpClient(name="geocoding") as opened:
                return await self.resolve(city, client=opened)

        async def search(name: str, country: str | None = None) -> tuple[Location, ...]:
            params: dict[str, Any] = {"name": name, "count": 10, "language": "en", "format": "json"}
            if country:
                params["countryCode"] = country
            data = await client.get_json(self.BASE_URL, params=params, breaker=get_geo_breaker())
            candidates = tuple(
                Location(**{k: r[k] for k in Location.__dataclass_fields__ if k in r})
                for r in (data.get("results") or [])[:10]
            )
            return tuple(c for c in candidates if not country or c.country_code == country)

        candidates = await search(city)
        country = None
        if "," in city:
            name, suffix = (p.strip() for p in city.rsplit(",", 1))
            country = COUNTRY_ALIASES.get(suffix.casefold())
            region = REGION_ALIASES.get(suffix.casefold(), suffix.casefold())
            # Native region matches take precedence over overlapping country aliases (CA).
            regional = tuple(c for c in candidates if (c.admin1 or "").casefold() == region)
            if regional:
                candidates, country = regional, None
            elif country:
                candidates = tuple(c for c in candidates if c.country_code == country)
                if not candidates:
                    candidates = await search(name, country)
            else:
                # Unknown qualifier must be represented in provider identity, not dropped.
                candidates = tuple(
                    c
                    for c in candidates
                    if suffix.casefold()
                    in {
                        (c.country or "").casefold(),
                        (c.admin1 or "").casefold(),
                        (c.country_code or "").casefold(),
                    }
                )
        if not candidates:
            raise NoDataError(
                f"No location found for city '{city}' with the supplied qualifier. "
                "Check spelling and use a full region name or a supported country alias; "
                "the qualifier was not discarded."
            )
        resolved = ResolvedLocation(candidates[0], candidates, city, country)
        cache.set_location(city, resolved)
        return resolved
