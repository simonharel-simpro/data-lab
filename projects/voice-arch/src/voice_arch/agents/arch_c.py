"""Architecture C: B plus a structured call record injected into each task's instructions."""

from livekit.agents import function_tool
from livekit.agents.beta.workflows import TaskGroup

from voice_arch.agents.arch_b import StepTask, build_task_group
from voice_arch.agents.tools import Ctx
from voice_arch.booking.actions import NOTED, apply_choose_slot, apply_record, render_call_record


@function_tool(description="Read back the call record: the filled fields, the missing ones and the corrections.")
async def read_record(ctx: Ctx) -> str:
    return render_call_record(ctx.userdata.record)


@function_tool(
    description="Set or correct one field of the call record: name, phone, address, problem_type or slot_id."
)
async def update_record(ctx: Ctx, field: str, value: str) -> str:
    """Never completes a task. A slot goes through the same availability rules as `choose_slot`."""
    state = ctx.userdata
    if field == "slot_id":
        reply = apply_choose_slot(state.record, value, state.taken)
        if state.record.slot_id == value:
            state.note_write()
        return reply
    reply = apply_record(state.record, field, value)
    if reply == NOTED:
        state.note_write()
    return reply


def _memory_task(cls: type[StepTask]) -> StepTask:
    return cls(memory=True, extra_tools=(read_record, update_record))


def build_task_group_c() -> TaskGroup:
    return build_task_group(_memory_task)
