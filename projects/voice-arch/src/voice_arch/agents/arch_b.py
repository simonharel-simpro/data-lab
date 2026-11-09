"""Architecture B: a `TaskGroup` of one custom `AgentTask` per step, regression allowed (U-18).

Custom tasks, not LiveKit's built-in Get*Task: their own instructions would break the shared-instruction rule.
The tools in `agents/tools.py` are the only write path and complete the task that owns the written field.
"""

from collections.abc import Callable, Sequence
from functools import partial
from typing import ClassVar, Final

from livekit.agents import Agent, AgentTask, llm
from livekit.agents.beta.workflows import TaskGroup

from voice_arch.agents.state import session_of
from voice_arch.agents.tools import (
    check_slots,
    choose_slot,
    confirm_booking,
    record_address,
    record_name,
    record_phone,
    record_problem,
)
from voice_arch.booking import instructions as text
from voice_arch.booking.actions import render_call_record

SUMMARIZE_CHAT_CTX: Final = False  # F-15: summarising adds an LLM call; off, and logged in every result

type Tools = Sequence[llm.Tool | llm.Toolset]


def ends_with_user_turn(ctx: llm.ChatContext) -> llm.ChatContext:
    """A copy of `ctx` whose last item is a user message: Gemini rejects a request ending with a model turn."""
    copy = ctx.copy()
    last = copy.items[-1] if copy.items else None
    if not (isinstance(last, llm.ChatMessage) and last.role == "user"):
        copy.add_message(role="user", content=[text.CALLER_WAITING])
    return copy


class StepTask(AgentTask[None]):
    FIELD: ClassVar[str]
    ASK: ClassVar[str]
    STEP_TOOLS: ClassVar[Tools]

    def __init__(self, *, memory: bool = False, extra_tools: Tools = ()) -> None:
        self._base = f"{text.CONTEXT} {self.ASK}"
        self._memory = memory
        super().__init__(  # pyright: ignore[reportUnknownMemberType]  # AgentTask.__init__ takes STT[Unknown]
            instructions=self._base, tools=[*self.STEP_TOOLS, *extra_tools]
        )

    async def on_enter(self) -> None:
        # An AgentTask's default on_enter says nothing, so without this the task stays silent.
        if self._memory:
            state = session_of(self).userdata
            await self.update_instructions(f"{self._base}\n\n{render_call_record(state.record)}")
        session_of(self).generate_reply(chat_ctx=ends_with_user_turn(self.chat_ctx))


class NameTask(StepTask):
    FIELD, ASK, STEP_TOOLS = "name", text.ASK_NAME, (record_name,)


class PhoneTask(StepTask):
    FIELD, ASK, STEP_TOOLS = "phone", text.ASK_PHONE, (record_phone,)


class AddressTask(StepTask):
    FIELD, ASK, STEP_TOOLS = "address", text.ASK_ADDRESS, (record_address,)


class ProblemTask(StepTask):
    FIELD, ASK, STEP_TOOLS = "problem_type", text.ASK_PROBLEM, (record_problem,)


class SlotTask(StepTask):
    FIELD, ASK, STEP_TOOLS = "slot_id", text.ASK_SLOT, (check_slots, choose_slot)


class ConfirmTask(StepTask):
    FIELD, ASK, STEP_TOOLS = "confirmed", text.CONFIRM, (confirm_booking,)


STEPS: Final[tuple[tuple[str, str, type[StepTask]], ...]] = (
    ("name", "collect the caller's name", NameTask),
    ("phone", "collect the caller's phone number", PhoneTask),
    ("address", "collect the service address", AddressTask),
    ("problem", "find out the type of problem", ProblemTask),
    ("slot", "choose the appointment slot", SlotTask),
    ("confirm", "read the booking back and confirm it", ConfirmTask),
)

type StepFactory = Callable[[type[StepTask]], StepTask]


def _plain(cls: type[StepTask]) -> StepTask:
    return cls()


def build_task_group(make: StepFactory = _plain) -> TaskGroup:
    group = TaskGroup(summarize_chat_ctx=SUMMARIZE_CHAT_CTX)
    for step_id, description, cls in STEPS:
        group.add(  # pyright: ignore[reportUnknownMemberType]  # TaskGroup.add takes AgentTask[Unknown]
            partial(make, cls), id=step_id, description=description
        )
    return group


class BookingFlowAgent(Agent):
    def __init__(self, make_group: Callable[[], TaskGroup] = build_task_group) -> None:
        super().__init__(  # pyright: ignore[reportUnknownMemberType]  # Agent.__init__ takes STT[Unknown]
            instructions=f"{text.CONTEXT} {text.GREETING}"
        )
        self._make_group = make_group

    async def on_enter(self) -> None:
        await session_of(self).generate_reply(instructions=text.GREETING)  # F-8: the only greeting
        await self._make_group()
