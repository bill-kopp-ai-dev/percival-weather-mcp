"""Shared HTTP client with retry/backoff, circuit breaking and concurrency control.

This module centralises outbound HTTP traffic so that all Open-Meteo services
benefit from the same resilience policy (timeouts, retries with jittered
exponential backoff, optional circuit breaker for geocoding, and a global
asyncio semaphore to cap concurrent in-flight requests).
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

import httpx

from .config import Settings, get_settings
from .observability import record_http_error, record_http_request

logger = logging.getLogger("mcp-weather.http")


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


class CircuitOpenError(RuntimeError):
    """Raised when the upstream is currently short-circuited."""


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
        if breaker is not None and not await breaker.allow():
            raise CircuitOpenError(f"circuit open for upstream '{self._name}'")

        attempts = self._settings.http_max_retries + 1
        last_exc: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                async with self._semaphore:
                    response = await self.raw.request(method, url, params=params)
                status = response.status_code
                # Always record the request count, regardless of status code or
                # retry decision, so error-path volume is visible in metrics.
                record_http_request(self._name, str(status))
                if status == httpx.codes.TOO_MANY_REQUESTS and attempt < attempts:
                    await self._sleep_backoff(attempt)
                    continue
                if status >= 500 and attempt < attempts:
                    await self._sleep_backoff(attempt)
                    continue
                if status != 200:
                    raise ValueError(f"{self._name} returned HTTP {status} for {url}")

                if breaker is not None:
                    await breaker.record_success()
                return response.json()
            except (httpx.RequestError, ValueError) as exc:
                record_http_error(self._name, exc)
                last_exc = exc
                if breaker is not None:
                    await breaker.record_failure()
                if attempt >= attempts:
                    raise
                await self._sleep_backoff(attempt)

        # Defensive: loop should always raise or return.
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("HTTP request failed without an exception")

    async def _sleep_backoff(self, attempt: int) -> None:
        base = self._settings.http_backoff_base
        cap = self._settings.http_backoff_cap
        delay = min(cap, base * (2 ** (attempt - 1)))
        delay += random.uniform(0, base)
        await asyncio.sleep(delay)


# ----------------------------------------------------------------------------
# Module-level singletons for the shared client and the geocoding breaker.
# These are created lazily so tests can override them.
# ----------------------------------------------------------------------------

_shared_client: ResilientHttpClient | None = None
_geo_breaker: CircuitBreaker | None = None


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


def reset_shared_state() -> None:
    """Reset module-level singletons (intended for tests)."""
    global _shared_client, _geo_breaker
    _shared_client = None
    _geo_breaker = None
