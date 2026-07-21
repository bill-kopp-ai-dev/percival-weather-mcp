"""Base ToolHandler class for extensible MCP tool management.

This follows the architecture pattern from mcp-gsuite for easy extension.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from mcp.types import (
    EmbeddedResource,
    ImageContent,
    TextContent,
    Tool,
)
from pydantic import BaseModel


class ToolHandler(ABC):
    """Abstract base class for all MCP tool handlers.

    Subclasses provide:
    * ``input_model`` - a Pydantic model describing the tool input.
    * ``run(args)`` - the actual logic that returns MCP content items.

    FastMCP consumes ``input_model`` to derive the JSON schema; legacy code
    that calls :meth:`run_tool` directly keeps working unchanged.
    """

    #: Identifier used by MCP (``weather_get_current`` etc.)
    name: str

    #: Short description surfaced to clients.
    description: str

    #: Pydantic model describing the input payload.
    input_model: type[BaseModel]

    def __init__(self, tool_name: str) -> None:
        self.name = tool_name

    @abstractmethod
    def get_tool_description(self) -> Tool:
        """Return the MCP Tool description for this handler."""
        raise NotImplementedError("Each tool handler must implement get_tool_description")

    @abstractmethod
    async def run_tool(
        self, args: dict
    ) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        """Execute the tool with the provided arguments (already validated)."""
        raise NotImplementedError("Each tool handler must implement run_tool")

    def parse_args(self, args: dict) -> BaseModel:
        """Validate and coerce ``args`` using :attr:`input_model`."""
        return self.input_model.model_validate(args)

    def validate_required_args(self, args: dict, required_fields: list[str]) -> None:
        """Raise :class:`RuntimeError` if any required field is missing."""
        missing = [field for field in required_fields if field not in args]
        if missing:
            raise RuntimeError(f"Missing required arguments: {', '.join(missing)}")
