"""Regression tests for ``GetWeatherByDateRangeInput`` range validation.

The 0.8.0 release delegated range validation to the service layer, which
surfaced confusing "end_date must be on or after start_date" messages via
the generic "Invalid weather request" path. Moving the check into a
Pydantic ``model_validator`` lets us catch the issue at the schema level
so the structured error reaches the agent before any HTTP call.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from percival_weather_mcp.models import GetWeatherByDateRangeInput


def test_valid_range_is_accepted():
    model = GetWeatherByDateRangeInput.model_validate(
        {"city": "Lisbon", "start_date": "2026-03-01", "end_date": "2026-03-07"}
    )
    assert model.start_date == "2026-03-01"
    assert model.end_date == "2026-03-07"


def test_inverted_range_is_rejected_by_pydantic():
    with pytest.raises(ValidationError) as info:
        GetWeatherByDateRangeInput.model_validate(
            {"city": "Lisbon", "start_date": "2026-03-10", "end_date": "2026-03-01"}
        )
    message = str(info.value)
    assert "end_date" in message
    assert "on or after" in message


def test_single_day_range_is_accepted():
    model = GetWeatherByDateRangeInput.model_validate(
        {"city": "Lisbon", "start_date": "2026-03-01", "end_date": "2026-03-01"}
    )
    assert model.start_date == "2026-03-01"
