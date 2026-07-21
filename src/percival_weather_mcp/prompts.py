"""MCP prompts exposed by the server.

Prompts are pre-written templates that the agent can fetch via
``prompts/list`` + ``prompts/get`` to obtain a recipe for a recurring task.
They encode best practices and steer the agent toward the right combination of
tools/resources.

Available prompts:

* ``weather_quick_answer`` — recipe for single-question answers ("how is the
  weather in X?").
* ``weather_analysis`` — recipe for range / multi-city analyses.
* ``weather_unit_conversion`` — recipe for timezone / unit conversions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.server.fastmcp.prompts.base import AssistantMessage, UserMessage

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def register_prompts(mcp_server: FastMCP) -> None:
    """Attach every prompt template to the given FastMCP server."""

    @mcp_server.prompt(
        name="weather_quick_answer",
        description=(
            "Recipe for answering a single weather question such as "
            "'How is the weather in <city> right now?'. Returns the system "
            "guidance the agent should follow and a user message template "
            "containing the city argument."
        ),
    )
    async def weather_quick_answer(city: str) -> list[AssistantMessage | UserMessage]:
        """Build the prompt for a one-shot weather question."""
        system_text = (
            "You are a weather assistant backed by the percival-weather-mcp server.\n"
            "\n"
            "For a single current-conditions question:\n"
            "  1. Call ``weather_get_current`` with ``city``. The tool returns a "
            "     plain-prose summary; surface it to the user as-is.\n"
            "  2. If the user also needs the raw fields, follow up with "
            "     ``weather_get_details`` (omit ``include_forecast`` unless "
            "     the user explicitly asks for a short-term forecast).\n"
            "  3. When the response mentions a numeric ``weather_code`` and the "
            "     user wants plain text, consult ``weather://codes``.\n"
            "  4. On error, retry once with a less specific city name (drop the "
            "     country suffix); if it still fails, ask the user to clarify.\n"
            "\n"
            "Never call ``weather_get_by_range`` for current-conditions "
            "questions — it is intended for historical/forecast windows."
        )
        user_text = (
            f"What is the current weather in {city}? "
            "Use the percival-weather-mcp tools to answer."
        )
        return [
            AssistantMessage(content=system_text),
            UserMessage(content=user_text),
        ]

    @mcp_server.prompt(
        name="weather_analysis",
        description=(
            "Recipe for analysing weather across a date range or across "
            "multiple cities. Use when the user wants averages, extremes, "
            "comparisons, or 'what was the weather like last week?'."
        ),
    )
    async def weather_analysis(
        city: str, start_date: str, end_date: str
    ) -> list[AssistantMessage | UserMessage]:
        """Build the prompt for a date-range weather analysis."""
        system_text = (
            "You are a weather analyst backed by the percival-weather-mcp server.\n"
            "\n"
            "For a date-range analysis:\n"
            "  1. Call ``weather_get_by_range`` with ``city``, ``start_date`` and "
            "     ``end_date``. The range must be ≤ 16 days inclusive.\n"
            "  2. The tool returns a structured JSON payload with ``summary`` "
            "     statistics and an ``hourly_sample``. Use ``summary`` for "
            "     averages/extremes; use ``hourly_sample`` for charts or "
            "     hourly detail. Consult ``weather://schema/weather_get_by_range`` "
            "     if you need the exact keys.\n"
            "  3. Translate numeric ``weather_code`` values via "
            "     ``weather://codes`` before showing them to the user.\n"
            "  4. For multi-city comparisons, repeat the call per city and "
            "     aggregate the summaries yourself; never use "
            "     ``weather_get_current`` for analytical questions."
        )
        user_text = (
            f"Analyse the weather in {city} between {start_date} and {end_date}. "
            "Highlight averages, extremes and any notable conditions."
        )
        return [
            AssistantMessage(content=system_text),
            UserMessage(content=user_text),
        ]

    @mcp_server.prompt(
        name="weather_unit_conversion",
        description=(
            "Recipe for converting datetimes between timezones or for "
            "translating a casual 'what time is it in <city>?' into a tool "
            "call. Use when the user mentions another city, country or "
            "explicit IANA timezone."
        ),
    )
    async def weather_unit_conversion(
        datetime_str: str = "now",
        from_timezone: str = "UTC",
        to_timezone: str = "UTC",
    ) -> list[AssistantMessage | UserMessage]:
        """Build the prompt for a timezone conversion."""
        system_text = (
            "You are a timezone-conversion assistant.\n"
            "\n"
            "Workflow:\n"
            "  1. If the user gave a city but no IANA name, derive the timezone "
            "     from the city (e.g. 'Tokyo' → 'Asia/Tokyo') using "
            "     ``weather://timezones`` as a reference.\n"
            "  2. If the user said 'now' or did not specify a time, pass "
            "     ``datetime_str='now'`` to ``weather_convert_time``.\n"
            "  3. Otherwise, normalise the time into ISO 8601 and pass it as "
            "     ``datetime_str`` (trailing 'Z' is supported).\n"
            "  4. Always confirm the resulting ``converted_datetime`` by "
            "     calling ``weather_get_time`` on the target timezone and "
            "     comparing the two outputs when precision matters.\n"
            "  5. For UTC offsets or DST flags, prefer ``weather_get_timezone`` "
            "     over arithmetic on the converted datetime."
        )
        user_text = (
            f"Convert {datetime_str} from {from_timezone} to {to_timezone} "
            "and present the result clearly."
        )
        return [
            AssistantMessage(content=system_text),
            UserMessage(content=user_text),
        ]
