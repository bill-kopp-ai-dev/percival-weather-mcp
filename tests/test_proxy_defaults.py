"""Regression tests for ``_make_tool_proxy``.

Covers edge cases that the original 0.8.0 fix did not handle:

1. Fields declared with ``default_factory=`` (not ``default=``) used to
   leak :data:`pydantic_core.PydanticUndefined` into the rebuilt
   ``inspect.Parameter`` because the proxy compared ``field_info.default``
   against ``inspect.Parameter.empty`` (which it never equals). The
   resulting signature was invalid and FastMCP would refuse to derive
   a schema.

2. Fields whose ``default`` is :data:`None` must keep ``None`` as their
   signature default (NOT ``inspect.Parameter.empty``) so optional
   arguments stay optional.
"""

from __future__ import annotations

import inspect

from pydantic import BaseModel, Field

from percival_weather_mcp.server import _make_tool_proxy
from percival_weather_mcp.tools.toolhandler import ToolHandler


class _FactoryInput(BaseModel):
    counter: int = Field(default_factory=lambda: 7)
    note: str | None = None


class _FactoryHandler(ToolHandler):
    input_model = _FactoryInput

    def __init__(self) -> None:
        super().__init__("factory_tool")

    def get_tool_description(self):  # type: ignore[override]
        from mcp.types import Tool

        return Tool(
            name=self.name,
            description="synthetic handler covering default_factory and None defaults.",
            inputSchema=_FactoryInput.model_json_schema(),
        )

    async def run_tool(self, args):  # type: ignore[override]
        return []


def test_proxy_resolves_default_factory_to_its_value():
    """Regression: ``default_factory`` must be invoked to produce the signature default."""
    handler = _FactoryHandler()
    proxy = _make_tool_proxy(handler)
    sig = inspect.signature(proxy)
    counter_param = sig.parameters["counter"]
    assert counter_param.default == 7, (
        f"expected default to come from the factory (7), got {counter_param.default!r}"
    )
    assert counter_param.default is not inspect.Parameter.empty


def test_proxy_keeps_none_default_for_optional_field():
    """Optional fields with ``default=None`` must remain optional in the proxy."""
    handler = _FactoryHandler()
    proxy = _make_tool_proxy(handler)
    sig = inspect.signature(proxy)
    note_param = sig.parameters["note"]
    assert note_param.default is None
    assert note_param.default is not inspect.Parameter.empty


def test_proxy_annotations_match_factory_model():
    handler = _FactoryHandler()
    proxy = _make_tool_proxy(handler)
    assert set(proxy.__annotations__) == set(_FactoryInput.model_fields.keys())
