"""Time-related tool handlers for the MCP weather server."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import cast

from mcp import McpError
from mcp.types import EmbeddedResource, ImageContent, TextContent, Tool

from .. import utils
from ..models import (
    ConvertTimeInput,
    GetCurrentDateTimeInput,
    GetTimeZoneInfoInput,
)
from .toolhandler import ToolHandler

logger = logging.getLogger("mcp-weather")


class GetCurrentDateTimeToolHandler(ToolHandler):
    """Current datetime in a given IANA timezone."""

    input_model = GetCurrentDateTimeInput

    def __init__(self) -> None:
        super().__init__("weather_get_time")

    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description=(
                "Get the current local datetime for a specific IANA timezone. "
                "Returns structured JSON with timezone and ISO 8601 datetime."
            ),
            inputSchema=GetCurrentDateTimeInput.model_json_schema(),
        )

    async def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        try:
            self.validate_required_args(args, ["timezone_name"])
            payload = cast(GetCurrentDateTimeInput, self.parse_args(args))
            tz = utils.get_zoneinfo(payload.timezone_name)
            current_time = datetime.now(tz)
            time_result = utils.TimeResult(
                timezone=payload.timezone_name,
                datetime=current_time.isoformat(timespec="seconds"),
            )
            return [TextContent(type="text", text=json.dumps(time_result.model_dump(), indent=2))]
        except RuntimeError:
            raise
        except McpError as exc:
            logger.warning("Invalid timezone in get_current_datetime: %s", exc)
            raise RuntimeError("Invalid timezone") from exc
        except Exception:
            logger.exception("Unexpected error in get_current_datetime")
            raise RuntimeError(
                "Datetime service is temporarily unavailable. Please retry."
            ) from None


class GetTimeZoneInfoToolHandler(ToolHandler):
    """Timezone metadata (offset, DST, abbreviation) for an IANA timezone."""

    input_model = GetTimeZoneInfoInput

    def __init__(self) -> None:
        super().__init__("weather_get_timezone")

    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description=(
                "Get timezone metadata for an IANA timezone as structured JSON: "
                "current local time, UTC time, offset in hours, DST flag, and "
                "timezone abbreviation. Use this when the user asks about DST, "
                "UTC offset, or abbreviation (e.g. 'PST', 'CET')."
            ),
            inputSchema=GetTimeZoneInfoInput.model_json_schema(),
        )

    async def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        try:
            self.validate_required_args(args, ["timezone_name"])
            payload = cast(GetTimeZoneInfoInput, self.parse_args(args))
            tz = utils.get_zoneinfo(payload.timezone_name)
            current_time = datetime.now(tz)
            utc_time = datetime.now(timezone.utc)
            offset = current_time.utcoffset()
            offset_hours = offset.total_seconds() / 3600 if offset else 0
            dst = current_time.dst()
            info = {
                "timezone_name": payload.timezone_name,
                "current_local_time": current_time.isoformat(timespec="seconds"),
                "current_utc_time": utc_time.isoformat(timespec="seconds"),
                "utc_offset_hours": offset_hours,
                "is_dst": dst is not None and dst.total_seconds() > 0,
                "timezone_abbreviation": current_time.strftime("%Z"),
            }
            return [TextContent(type="text", text=json.dumps(info, indent=2))]
        except RuntimeError:
            raise
        except McpError as exc:
            logger.warning("Invalid timezone in get_timezone_info: %s", exc)
            raise RuntimeError("Invalid timezone") from exc
        except Exception:
            logger.exception("Unexpected error in get_timezone_info")
            raise RuntimeError(
                "Timezone service is temporarily unavailable. Please retry."
            ) from None


class ConvertTimeToolHandler(ToolHandler):
    """Timezone-aware datetime conversion."""

    input_model = ConvertTimeInput

    def __init__(self) -> None:
        super().__init__("weather_convert_time")

    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description=(
                "Convert a datetime from one timezone to another. Returns a JSON "
                "payload with the original and converted timestamps and the time "
                "difference in hours. Accepts 'now' or ISO 8601 input (including "
                "trailing 'Z')."
            ),
            inputSchema=ConvertTimeInput.model_json_schema(),
        )

    async def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        try:
            self.validate_required_args(args, ["datetime_str", "from_timezone", "to_timezone"])
            payload = cast(ConvertTimeInput, self.parse_args(args))
            from_tz = utils.get_zoneinfo(payload.from_timezone)
            to_tz = utils.get_zoneinfo(payload.to_timezone)

            if payload.datetime_str.strip().lower() == "now":
                source_time = datetime.now(from_tz)
            else:
                normalised = payload.datetime_str.replace("Z", "+00:00")
                parsed = datetime.fromisoformat(normalised)
                if parsed.tzinfo is None:
                    source_time = parsed.replace(tzinfo=from_tz)
                else:
                    source_time = parsed.astimezone(from_tz)

            target_time = source_time.astimezone(to_tz)
            src_offset = source_time.utcoffset() or timedelta(0)
            tgt_offset = target_time.utcoffset() or timedelta(0)
            result = {
                "original_datetime": source_time.isoformat(timespec="seconds"),
                "original_timezone": payload.from_timezone,
                "converted_datetime": target_time.isoformat(timespec="seconds"),
                "converted_timezone": payload.to_timezone,
                "time_difference_hours": (
                    tgt_offset.total_seconds() - src_offset.total_seconds()
                ) / 3600,
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        except RuntimeError:
            raise
        except McpError as exc:
            logger.warning("Invalid timezone in convert_time: %s", exc)
            raise RuntimeError("Invalid timezone") from exc
        except ValueError as exc:
            logger.warning("Invalid datetime input in convert_time: %s", exc)
            raise RuntimeError("Invalid datetime format") from exc
        except Exception:
            logger.exception("Unexpected error in convert_time")
            raise RuntimeError(
                "Time conversion service is temporarily unavailable. Please retry."
            ) from None
