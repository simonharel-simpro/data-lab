"""The booking tools, thin wrappers over `booking.actions` (U-26: names and args follow `TOOL_SCHEMAS`).

Under B and C a step task completes only when ITS OWN field was written (`FIELD`); under A nothing completes.
"""

from typing import Literal, cast

from livekit.agents import AgentTask, RunContext, function_tool

from voice_arch.agents.state import BookingState
from voice_arch.booking.actions import (
    CONFIRMED,
    NOTED,
    apply_check_slots,
    apply_choose_slot,
    apply_confirm,
    apply_record,
)
from voice_arch.booking.instructions import GOODBYE
from voice_arch.tool_schemas import TOOL_SCHEMAS

# Plain aliases, not `type` statements: LiveKit finds the RunContext parameter through the real annotation.
Ctx = RunContext[BookingState]
ProblemName = Literal["plumbing", "electrical", "hvac", "appliance", "other"]
_DESCRIPTIONS = {schema.name: schema.description for schema in TOOL_SCHEMAS}


def complete_current_task(ctx: Ctx, field: str) -> None:
    """Finish the running step task if it owns `field`; `complete` raises on a second call, hence the guard."""
    agent = ctx.session.current_agent
    if not isinstance(agent, AgentTask):
        return
    task = cast("AgentTask[None]", agent)  # step tasks are `AgentTask[None]`; the SDK's isinstance leaves it Unknown
    if not task.done() and getattr(task, "FIELD", None) == field:
        task.complete(None)


def _record(ctx: Ctx, field: str, value: str) -> str:
    reply = apply_record(ctx.userdata.record, field, value)
    if reply == NOTED:
        ctx.userdata.note_write()
        complete_current_task(ctx, field)
    return reply


@function_tool(description=_DESCRIPTIONS["record_name"])
async def record_name(ctx: Ctx, name: str) -> str:
    return _record(ctx, "name", name)


@function_tool(description=_DESCRIPTIONS["record_phone"])
async def record_phone(ctx: Ctx, phone: str) -> str:
    return _record(ctx, "phone", phone)


@function_tool(description=_DESCRIPTIONS["record_address"])
async def record_address(ctx: Ctx, address: str) -> str:
    return _record(ctx, "address", address)


@function_tool(description=_DESCRIPTIONS["record_problem"])
async def record_problem(ctx: Ctx, problem_type: ProblemName) -> str:
    return _record(ctx, "problem_type", problem_type)


@function_tool(
    description=(
        "List up to two free appointment slots with their ids. `day` is an ISO date such as 2026-11-10 "
        "(format YYYY-MM-DD, optional); `part` is morning or afternoon (optional)."
    )
)
async def check_slots(ctx: Ctx, day: str | None = None, part: str | None = None) -> str:
    return apply_check_slots(day, part, ctx.userdata.taken)


@function_tool(description=_DESCRIPTIONS["choose_slot"])
async def choose_slot(ctx: Ctx, slot_id: str) -> str:
    state = ctx.userdata
    reply = apply_choose_slot(state.record, slot_id, state.taken)
    if state.record.slot_id == slot_id:
        state.note_write()
        complete_current_task(ctx, "slot_id")
    return reply


@function_tool(description="Confirm the booking once the caller has agreed to the read-back.")
async def confirm_booking(ctx: Ctx) -> str:
    state = ctx.userdata
    reply = apply_confirm(
        state.record, caller_replied=state.caller_replied_since_write(lambda: ctx.session.history.items)
    )
    if reply == CONFIRMED:
        ctx.session.say(GOODBYE)
        ctx.session.shutdown(drain=True)  # F-1: the agent ends the call after the booking is confirmed
        complete_current_task(ctx, "confirmed")
    return reply


ALL_TOOLS = [record_name, record_phone, record_address, record_problem, check_slots, choose_slot, confirm_booking]
