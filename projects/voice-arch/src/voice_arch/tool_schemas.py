"""The five booking tools: one source for the stage-1 LLM bench and Phase 2's agent tools (U-26)."""

from collections.abc import Coroutine
from dataclasses import dataclass
from typing import Any, Final, Literal

from livekit.agents import function_tool
from livekit.agents.llm import RawFunctionTool

# `_noop` as `function_tool` wraps it; the Coroutine's send/yield slots are Any in typeshed's async def.
type RawTool = RawFunctionTool[[dict[str, object]], Coroutine[Any, Any, str]]

PROBLEM_TYPES: Final = ("plumbing", "electrical", "hvac", "appliance", "other")


@dataclass(frozen=True)
class ToolArg:
    name: str
    type: Literal["str", "problem_type", "slot_id"]


@dataclass(frozen=True)
class ToolSchema:
    name: str
    description: str
    args: tuple[ToolArg, ...]


TOOL_SCHEMAS: Final = (
    ToolSchema("record_name", "Record the caller's name.", (ToolArg("name", "str"),)),
    ToolSchema("record_phone", "Record the caller's phone number.", (ToolArg("phone", "str"),)),
    ToolSchema("record_address", "Record the service address.", (ToolArg("address", "str"),)),
    ToolSchema("record_problem", "Record the type of problem.", (ToolArg("problem_type", "problem_type"),)),
    ToolSchema("choose_slot", "Choose one of the offered appointment slots.", (ToolArg("slot_id", "slot_id"),)),
)


def _arg_schema(arg: ToolArg) -> dict[str, object]:
    if arg.type == "problem_type":
        return {"type": "string", "enum": list(PROBLEM_TYPES)}
    if arg.type == "slot_id":
        return {"type": "string", "description": "The id of an offered slot, e.g. ST_20261110_0900."}
    return {"type": "string"}


def _to_flat(schema: ToolSchema) -> dict[str, object]:
    return {
        "name": schema.name,
        "description": schema.description,
        "parameters": {
            "type": "object",
            "properties": {arg.name: _arg_schema(arg) for arg in schema.args},
            "required": [arg.name for arg in schema.args],
        },
    }


def to_openai_tools() -> list[dict[str, object]]:
    """Flat `{name, description, parameters}` dicts: what `function_tool(raw_schema=...)` expects."""
    return [_to_flat(schema) for schema in TOOL_SCHEMAS]


async def _noop(raw_arguments: dict[str, object]) -> str:
    return ""


def to_raw_tools() -> list[RawTool]:
    """Schema-only tool objects for `LLM.chat(tools=...)`: they are never executed."""
    return [function_tool(_noop, raw_schema=flat) for flat in to_openai_tools()]
