"""Tests for input sanitisation helpers."""

from __future__ import annotations

import pytest
from mcp import McpError

from percival_weather_mcp import utils


class TestNormalizeCityName:
    def test_collapses_whitespace(self):
        assert utils.normalize_city_name("  São   Paulo  ") == "São Paulo"

    def test_strips_control_characters(self):
        assert utils.normalize_city_name("Lon\x00don") == "London"

    def test_rejects_empty(self):
        with pytest.raises(ValueError):
            utils.normalize_city_name("   ")

    def test_rejects_non_string(self):
        with pytest.raises(ValueError):
            utils.normalize_city_name(123)  # type: ignore[arg-type]

    def test_rejects_forbidden_chars(self):
        with pytest.raises(ValueError):
            utils.normalize_city_name("New<York>")

    def test_enforces_max_length(self):
        with pytest.raises(ValueError):
            utils.normalize_city_name("a" * (utils.MAX_CITY_NAME_LENGTH + 1))


class TestSafeInlineText:
    def test_collapses_spaces_and_truncates(self):
        long_text = "x" * 500
        rendered = utils.safe_inline_text(long_text, max_length=10)
        assert rendered.startswith("xxxxxxxxxx")
        assert rendered.endswith("...")

    def test_handles_non_string(self):
        assert utils.safe_inline_text(123) == "123"


class TestGetZoneinfo:
    def test_valid_timezone(self):
        tz = utils.get_zoneinfo("America/Sao_Paulo")
        assert tz.key == "America/Sao_Paulo"

    def test_invalid_timezone(self):
        with pytest.raises(McpError):
            utils.get_zoneinfo("Not/A_Real_Zone")

    def test_forbidden_chars_rejected(self):
        with pytest.raises(McpError):
            utils.get_zoneinfo("..evil")

    def test_too_long_rejected(self):
        long_name = "A" * (utils.MAX_TIMEZONE_NAME_LENGTH + 1)
        with pytest.raises(McpError):
            utils.get_zoneinfo(long_name)

    def test_non_string_rejected(self):
        with pytest.raises(McpError):
            utils.get_zoneinfo(None)  # type: ignore[arg-type]


class TestGetClosestUtcIndex:
    def test_returns_closest(self):
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        times = [
            (now - timedelta(hours=2)).isoformat(),
            (now - timedelta(hours=1)).isoformat(),
            (now + timedelta(hours=1)).isoformat(),
            (now + timedelta(hours=2)).isoformat(),
        ]
        # The first time after ``now`` (index 2) must be chosen.
        index = utils.get_closest_utc_index(times)
        assert index == 2
