"""Shared HTTP client with retry/backoff, circuit breaking and concurrency control.

This module centralises outbound HTTP traffic so that all Open-Meteo services
benefit from the same resilience policy (timeouts, retries with jittered
exponential backoff, optional circuit breaker for geocoding, and a global
asyncio semaphore to cap concurrent in-flight requests).

Two rules govern the outbound policy:

* Only **recoverable** failures are retried: HTTP 429, HTTP 5xx, timeouts and
  transport errors. A non-recoverable 4xx is answered on the first attempt —
  repeating it would amplify load on a public, rate-limited API without any
  chance of a different outcome.
* Every failure leaves this module as an :class:`UpstreamError` carrying the
  external cause (status code, timeout, network error), so the tool layer can
  report the true reason to the agent instead of blaming the request.
"""

from __future__ import annotations

import asyncio
import logging
import random
import threading
from time import monotonic
from typing import Any
from urllib.parse import urlsplit

import httpx

from .config import Settings, get_settings
from .errors import (
    UpstreamError,
    service_label,
    upstream_http_error,
    upstream_invalid_response,
    upstream_timeout,
    upstream_unreachable,
)
from .observability import record_http_error, record_http_request

logger = logging.getLogger("mcp-weather.http")


#: The Open-Meteo services, keyed by host. The label names the service that
#: was actually called: one HTTP client can serve more than one upstream (the
#: air-quality tools geocode and then read the air-quality endpoint through
#: the same client), so the client name would mislabel the failure.
_SERVICE_BY_HOST: dict[str, str] = {
    "api.open-meteo.com": "weather forecast",
    "geocoding-api.open-meteo.com": "geocoding",
    "air-quality-api.open-meteo.com": "air quality",
}


def service_for_url(url: str, fallback: str) -> str:
    """Return the display label of the upstream service addressed by ``url``."""
    host = urlsplit(url).hostname or ""
    return _SERVICE_BY_HOST.get(host, service_label(fallback))


def is_retryable_status(status_code: int) -> bool:
    """Return True when an HTTP status is worth retrying.

    429 (rate limited) and 5xx (provider failure) are transient; every other
    4xx is a deterministic rejection of the request as sent.
    """
    return status_code == httpx.codes.TOO_MANY_REQUESTS or status_code >= 500


class CircuitBreaker:
    """Minimal circuit breaker: opens after ``fail_threshold`` consecutive errors."""

    def __init__(self, fail_threshold: int, reset_seconds: float) -> None:
        self._fail_threshold = max(1, fail_threshold)
        self._reset_seconds = max(0.1, reset_seconds)
        self._failures = 0
        self._opened_at: float | None = None
        self._lock = asyncio.Lock()

    async def allow(self) -> bool:
        async with self._lock:
            if self._opened_at is None:
                return True
            import time

            if (time.monotonic() - self._opened_at) >= self._reset_seconds:
                self._opened_at = None
                self._failures = 0
                logger.info("circuit breaker half-open: allowing probe request")
                return True
            return False

    async def record_success(self) -> None:
        async with self._lock:
            self._failures = 0
            self._opened_at = None

    async def record_failure(self) -> None:
        async with self._lock:
            # If the breaker is already open we keep the original open
            # timestamp so the cooldown window cannot be extended indefinitely
            # by a continuous stream of failures. Only the first opening is
            # recorded.
            if self._opened_at is not None:
                return
            self._failures += 1
            if self._failures >= self._fail_threshold:
                import time

                self._opened_at = time.monotonic()
                logger.warning(
                    "circuit breaker opened after %s failures; cooling down for %.1fs",
                    self._failures,
                    self._reset_seconds,
                )


class CircuitOpenError(UpstreamError):
    """Raised when the upstream is currently short-circuited.

    It is an :class:`UpstreamError` so the tool layer treats a short-circuited
    call exactly like any other upstream failure — the agent must retry later
    rather than change its input.
    """

    def __init__(self, service: str) -> None:
        message = (
            f"Upstream Open-Meteo {service_label(service)} is temporarily disabled after "
            "repeated failures. Retry shortly."
        )
        super().__init__(message, service=service, reason="circuit_open")


class ResilientHttpClient:
    """Wraps :class:`httpx.AsyncClient` with retry, breaker and semaphore."""

    def __init__(self, settings: Settings | None = None, *, name: str = "default") -> None:
        self._settings = settings or get_settings()
        self._name = name
        self._client: httpx.AsyncClient | None = None
        self._semaphore = asyncio.Semaphore(self._settings.http_max_concurrency)

    async def __aenter__(self) -> ResilientHttpClient:
        self._client = httpx.AsyncClient(timeout=self._settings.http_timeout)
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def raw(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("ResilientHttpClient must be used as an async context manager")
        return self._client

    async def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        breaker: CircuitBreaker | None = None,
    ) -> dict[str, Any]:
        return await self._request_json("GET", url, params=params, breaker=breaker)

    async def _request_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        breaker: CircuitBreaker | None = None,
    ) -> dict[str, Any]:
        error: UpstreamError
        if breaker is not None and not await breaker.allow():
            error = CircuitOpenError(self._name)
            record_http_error(self._name, error)
            raise error

        attempts = max(1, self._settings.http_max_retries + 1)
        last_error: UpstreamError | None = None
        label = service_for_url(url, self._name)

        for attempt in range(1, attempts + 1):
            try:
                async with self._semaphore:
                    response = await self.raw.request(method, url, params=params)
            except httpx.TimeoutException as exc:
                error = upstream_timeout(label, self._settings.http_timeout)
                record_http_error(self._name, error)
                last_error = error
                if breaker is not None:
                    await breaker.record_failure()
                if attempt >= attempts:
                    raise error from exc
                await self._sleep_backoff(attempt)
                continue
            except httpx.RequestError as exc:
                error = upstream_unreachable(label, type(exc).__name__)
                record_http_error(self._name, error)
                last_error = error
                if breaker is not None:
                    await breaker.record_failure()
                if attempt >= attempts:
                    raise error from exc
                await self._sleep_backoff(attempt)
                continue

            status = response.status_code
            # Always record the request count, regardless of status code or
            # retry decision, so error-path volume is visible in metrics.
            record_http_request(self._name, str(status))

            if status == httpx.codes.OK:
                try:
                    payload = response.json()
                except ValueError as exc:
                    error = upstream_invalid_response(label)
                    record_http_error(self._name, error)
                    if breaker is not None:
                        await breaker.record_failure()
                    raise error from exc
                if not isinstance(payload, dict):
                    error = upstream_invalid_response(label)
                    record_http_error(self._name, error)
                    if breaker is not None:
                        await breaker.record_failure()
                    raise error
                if breaker is not None:
                    await breaker.record_success()
                return payload

            error = upstream_http_error(label, status)
            record_http_error(self._name, error)
            last_error = error
            if breaker is not None:
                await breaker.record_failure()
            if attempt >= attempts or not is_retryable_status(status):
                # A non-recoverable status (4xx other than 429) is answered on
                # the first attempt: repeating it cannot change the outcome
                # and would only add load to the public upstream.
                raise error
            await self._sleep_backoff(attempt)

        # Defensive: the loop always raises or returns.
        raise last_error or upstream_unreachable(label, "no attempt was made")

    async def _sleep_backoff(self, attempt: int) -> None:
        base = self._settings.http_backoff_base
        cap = self._settings.http_backoff_cap
        delay = min(cap, base * (2 ** (attempt - 1)))
        delay += random.uniform(0, base)
        await asyncio.sleep(delay)


class GeocodingCache:
    """Process-wide, TTL-bounded cache of geocoded coordinates.

    Every tool handler used to build its own :class:`WeatherService`, and
    therefore its own cache: four logical queries for the same city spread
    over two tools cost three geocoding calls against a public, rate-limited
    API. The cache is now shared by the whole process, with the same TTL and
    size bounds it always had.

    Access is guarded by a plain lock: the cache is touched from the event
    loop and from worker threads, and it must never hand out a half-written
    entry.
    """

    def __init__(self, *, ttl_seconds: float | None = None, max_size: int | None = None) -> None:
        settings = get_settings()
        self._ttl_seconds = (
            ttl_seconds if ttl_seconds is not None else settings.geo_cache_ttl_seconds
        )
        self._max_size = max_size if max_size is not None else settings.geo_cache_max_size
        self._entries: dict[str, tuple[float, float, float]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(city: str) -> str:
        return city.strip().lower()

    def get(self, city: str) -> tuple[float, float] | None:
        """Return the cached coordinates for ``city``, or ``None`` when absent/expired."""
        key = self._key(city)
        with self._lock:
            cached = self._entries.get(key)
            if cached is None:
                return None
            latitude, longitude, expires_at = cached
            if monotonic() >= expires_at:
                self._entries.pop(key, None)
                return None
            return latitude, longitude

    def set(self, city: str, latitude: float, longitude: float) -> None:
        """Store the coordinates for ``city``, evicting the oldest entry if needed."""
        key = self._key(city)
        with self._lock:
            if key not in self._entries and len(self._entries) >= self._max_size:
                oldest_key = min(self._entries, key=lambda candidate: self._entries[candidate][2])
                self._entries.pop(oldest_key, None)
            self._entries[key] = (latitude, longitude, monotonic() + self._ttl_seconds)

    def clear(self) -> None:
        """Drop every entry."""
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


# ----------------------------------------------------------------------------
# Module-level singletons for the shared client and the geocoding breaker.
# These are created lazily so tests can override them.
# ----------------------------------------------------------------------------

_shared_client: ResilientHttpClient | None = None
_geo_breaker: CircuitBreaker | None = None
_geo_cache: GeocodingCache | None = None


def get_shared_client() -> ResilientHttpClient:
    """Return the lazily-created shared HTTP client.

    The returned object is **not** open; callers must use it as an async context
    manager (``async with get_shared_client() as client: ...``).
    """
    global _shared_client
    if _shared_client is None:
        _shared_client = ResilientHttpClient(name="shared")
    return _shared_client


def get_geo_breaker() -> CircuitBreaker:
    """Return the lazily-created geocoding circuit breaker."""
    global _geo_breaker
    settings = get_settings()
    if _geo_breaker is None:
        _geo_breaker = CircuitBreaker(
            fail_threshold=settings.geo_breaker_fail_threshold,
            reset_seconds=settings.geo_breaker_reset_seconds,
        )
    return _geo_breaker


def get_geocoding_cache() -> GeocodingCache:
    """Return the lazily-created process-wide geocoding cache."""
    global _geo_cache
    if _geo_cache is None:
        _geo_cache = GeocodingCache()
    return _geo_cache


def reset_shared_state() -> None:
    """Reset module-level singletons (intended for tests)."""
    global _shared_client, _geo_breaker, _geo_cache
    _shared_client = None
    _geo_breaker = None
    _geo_cache = None
