"""Conservative Forecast API policy; archive/reanalysis is a separate product."""

from datetime import date, datetime, timedelta

from . import series
from .config import get_settings
from .errors import InvalidRequestError

PAST_DAYS = 92
FUTURE_DAYS = 15


def validate_range(
    start_date: str, end_date: str, *, reference: datetime | None = None
) -> tuple[str, str]:
    try:
        start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    except ValueError as exc:
        raise InvalidRequestError(
            "start_date and end_date must use YYYY-MM-DD calendar dates."
        ) from exc
    if end < start:
        raise InvalidRequestError("end_date must be on or after start_date.")
    limit = get_settings().max_date_range_days
    if (end - start).days + 1 > limit:
        raise InvalidRequestError(
            f"Date range exceeds {limit} days inclusive; use a shorter interval."
        )
    today = (reference or series.utc_now()).date()
    earliest, latest = today - timedelta(days=PAST_DAYS), today + timedelta(days=FUTURE_DAYS)
    if start < earliest or end > latest:
        raise InvalidRequestError(
            f"start_date/end_date outside supported Forecast API window: {earliest} through {latest} "
            f"(UTC, inclusive; today-{PAST_DAYS} to today+{FUTURE_DAYS} days). "
            "Archive data is not supported by this tool."
        )
    return start.isoformat(), end.isoformat()
