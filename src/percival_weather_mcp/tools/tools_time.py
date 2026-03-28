"""
Time-related tool handlers for the MCP weather server.
This module contains time and timezone-related tool implementations.
"""

import json
import logging
from collections.abc import Sequence
from datetime import datetime
from mcp import McpError
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource
from .toolhandler import ToolHandler
from .. import utils

logger = logging.getLogger("mcp-weather")


class GetCurrentDateTimeToolHandler(ToolHandler):
    """
    Tool handler for getting current date and time in a specified timezone.
    """

    def __init__(self):
        super().__init__("get_current_datetime")

    def get_tool_description(self) -> Tool:
        """
        Return the MCP contract for current datetime in a target timezone.
        """
        return Tool(
            name=self.name,
            description=(
                "Get the current local datetime for a specific IANA timezone. "
                "Returns structured JSON with timezone and ISO 8601 datetime."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "timezone_name": {
                        "type": "string",
                        "description": (
                            "IANA timezone name (for example: 'America/New_York', "
                            "'Europe/London', 'UTC')."
                        ),
                    }
                },
                "required": ["timezone_name"]
            }
        )

    async def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        """
        Execute current datetime lookup and return JSON text.
        """
        try:
            self.validate_required_args(args, ["timezone_name"])

            timezone_name = args["timezone_name"]
            logger.info(f"Getting current time for timezone: {timezone_name}")

            # Get timezone info
            timezone = utils.get_zoneinfo(timezone_name)
            current_time = datetime.now(timezone)

            # Create time result
            time_result = utils.TimeResult(
                timezone=timezone_name,
                datetime=current_time.isoformat(timespec="seconds"),
            )

            return [
                TextContent(
                    type="text",
                    text=json.dumps(time_result.model_dump(), indent=2)
                )
            ]
        except RuntimeError:
            raise
        except McpError as e:
            logger.warning("Invalid timezone in get_current_datetime: %s", e)
            raise RuntimeError("Invalid timezone") from e
        except Exception:
            logger.exception("Unexpected error in get_current_datetime")
            raise RuntimeError("Datetime service is temporarily unavailable. Please retry.") from None


class GetTimeZoneInfoToolHandler(ToolHandler):
    """
    Tool handler for getting information about timezones.
    """

    def __init__(self):
        super().__init__("get_timezone_info")

    def get_tool_description(self) -> Tool:
        """
        Return the MCP contract for timezone metadata lookup.
        """
        return Tool(
            name=self.name,
            description=(
                "Get timezone metadata for an IANA timezone: current local time, UTC time, "
                "offset in hours, DST flag, and timezone abbreviation."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "timezone_name": {
                        "type": "string",
                        "description": (
                            "IANA timezone name (for example: 'America/Sao_Paulo', 'Asia/Tokyo')."
                        ),
                    }
                },
                "required": ["timezone_name"]
            }
        )

    async def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        """
        Execute timezone metadata lookup and return JSON text.
        """
        try:
            self.validate_required_args(args, ["timezone_name"])

            timezone_name = args["timezone_name"]
            logger.info(f"Getting timezone info for: {timezone_name}")

            # Get timezone info
            timezone = utils.get_zoneinfo(timezone_name)
            current_time = datetime.now(timezone)
            utc_time = datetime.utcnow()

            # Calculate UTC offset
            offset = current_time.utcoffset()
            offset_hours = offset.total_seconds() / 3600 if offset else 0

            timezone_info = {
                "timezone_name": timezone_name,
                "current_local_time": current_time.isoformat(timespec="seconds"),
                "current_utc_time": utc_time.isoformat(timespec="seconds"),
                "utc_offset_hours": offset_hours,
                "is_dst": current_time.dst() is not None and current_time.dst().total_seconds() > 0,
                "timezone_abbreviation": current_time.strftime("%Z"),
            }

            return [
                TextContent(
                    type="text",
                    text=json.dumps(timezone_info, indent=2)
                )
            ]
        except RuntimeError:
            raise
        except McpError as e:
            logger.warning("Invalid timezone in get_timezone_info: %s", e)
            raise RuntimeError("Invalid timezone") from e
        except Exception:
            logger.exception("Unexpected error in get_timezone_info")
            raise RuntimeError("Timezone service is temporarily unavailable. Please retry.") from None


class ConvertTimeToolHandler(ToolHandler):
    """
    Tool handler for converting time between different timezones.
    """

    def __init__(self):
        super().__init__("convert_time")

    def get_tool_description(self) -> Tool:
        """
        Return the MCP contract for timezone-aware datetime conversion.
        """
        return Tool(
            name=self.name,
            description=(
                "Convert a datetime from one timezone to another. "
                "Accepts 'now' or ISO 8601 input; supports offset-aware strings "
                "(including trailing 'Z')."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "datetime_str": {
                        "type": "string",
                        "description": (
                            "Datetime to convert: 'now' or ISO 8601 string "
                            "(for example: '2026-03-28T14:30:00' or '2026-03-28T14:30:00Z'). "
                            "If timezone is omitted, it is interpreted in from_timezone."
                        ),
                    },
                    "from_timezone": {
                        "type": "string",
                        "description": "Source timezone (IANA name).",
                    },
                    "to_timezone": {
                        "type": "string",
                        "description": "Target timezone (IANA name).",
                    }
                },
                "required": ["datetime_str", "from_timezone", "to_timezone"]
            }
        )

    async def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        """
        Execute timezone conversion and return JSON with original/converted values.
        """
        try:
            self.validate_required_args(args, ["datetime_str", "from_timezone", "to_timezone"])

            datetime_str = args["datetime_str"]
            from_timezone_name = args["from_timezone"]
            to_timezone_name = args["to_timezone"]

            logger.info(f"Converting time '{datetime_str}' from {from_timezone_name} to {to_timezone_name}")

            # Get timezone objects
            from_timezone = utils.get_zoneinfo(from_timezone_name)
            to_timezone = utils.get_zoneinfo(to_timezone_name)

            # Parse the datetime.
            # If input is offset-aware (for example with a trailing 'Z'),
            # interpret it as an absolute timestamp, then represent it in from_timezone.
            if datetime_str.lower() == "now":
                source_time = datetime.now(from_timezone)
            else:
                normalized_datetime_str = datetime_str.replace("Z", "+00:00")
                parsed_time = datetime.fromisoformat(normalized_datetime_str)
                if parsed_time.tzinfo is None:
                    # Naive input: assume it belongs to from_timezone
                    source_time = parsed_time.replace(tzinfo=from_timezone)
                else:
                    # Aware input: keep the same instant and express it in from_timezone
                    source_time = parsed_time.astimezone(from_timezone)

            # Convert to target timezone
            target_time = source_time.astimezone(to_timezone)

            conversion_result = {
                "original_datetime": source_time.isoformat(timespec="seconds"),
                "original_timezone": from_timezone_name,
                "converted_datetime": target_time.isoformat(timespec="seconds"),
                "converted_timezone": to_timezone_name,
                "time_difference_hours": (target_time.utcoffset().total_seconds() - source_time.utcoffset().total_seconds()) / 3600
            }

            return [
                TextContent(
                    type="text",
                    text=json.dumps(conversion_result, indent=2)
                )
            ]
        except RuntimeError:
            raise
        except McpError as e:
            logger.warning("Invalid timezone in convert_time: %s", e)
            raise RuntimeError("Invalid timezone") from e
        except ValueError as e:
            logger.warning("Invalid datetime input in convert_time: %s", e)
            raise RuntimeError("Invalid datetime format") from e
        except Exception:
            logger.exception("Unexpected error in convert_time")
            raise RuntimeError("Time conversion service is temporarily unavailable. Please retry.") from None
