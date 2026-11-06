from types import SimpleNamespace
from typing import cast

from livekit.agents import RunContext
from livekit.agents.llm import utils as llm_utils

from voice_arch.agents import tools
from voice_arch.agents.arch_b import PhoneTask, SlotTask
from voice_arch.agents.state import BookingState
from voice_arch.booking.instructions import GOODBYE
from voice_arch.booking.record import ProblemType
from voice_arch.tool_schemas import TOOL_SCHEMAS


class FakeSession:
    """Records the two session calls `confirm_booking` makes; `current_agent` is the real task under test."""

    def __init__(self, current_agent: object) -> None:
        self.current_agent = current_agent
        self.said: list[str] = []
        self.shutdowns: list[bool] = []

    def say(self, text: str) -> None:
        self.said.append(text)

    def shutdown(self, *, drain: bool) -> None:
        self.shutdowns.append(drain)


def _ctx(session: FakeSession, state: BookingState) -> RunContext[BookingState]:
    return cast("RunContext[BookingState]", SimpleNamespace(session=session, userdata=state))


async def test_correction_of_another_field_does_not_complete_the_task() -> None:
    state, task = BookingState(), SlotTask()
    ctx = _ctx(FakeSession(task), state)

    reply = await tools.record_phone(ctx, "415 555 0134")

    assert reply == "Noted."
    assert state.record.phone == "415 555 0134"
    assert task.done() is False


async def test_choose_slot_completes_the_slot_task_once() -> None:
    state, task = BookingState(), SlotTask()
    ctx = _ctx(FakeSession(task), state)

    first = await tools.choose_slot(ctx, "ST_20261110_1400")
    second = await tools.choose_slot(ctx, "ST_20261110_1400")

    assert task.done() is True
    assert first == second  # a repeat on a finished task is a plain reply, not a double complete()
    assert state.record.slot_id == "ST_20261110_1400"


async def test_failed_choose_slot_does_not_complete_the_task() -> None:
    task = SlotTask()
    ctx = _ctx(FakeSession(task), BookingState())

    reply = await tools.choose_slot(ctx, "ST_20261109_0900")

    assert "taken" in reply
    assert task.done() is False


async def test_record_under_architecture_a_completes_nothing() -> None:
    state = BookingState()
    ctx = _ctx(FakeSession(object()), state)

    assert await tools.record_name(ctx, "Jon") == "Noted."


async def test_record_phone_completes_the_phone_task() -> None:
    task = PhoneTask()
    ctx = _ctx(FakeSession(task), BookingState())

    reply = await tools.record_phone(ctx, "415 555 0134")

    assert reply == "Noted."
    assert task.done() is True


async def test_record_problem_with_invalid_type_returns_error_text() -> None:
    state = BookingState()
    ctx = _ctx(FakeSession(object()), state)

    reply = await tools.record_problem(ctx, "roofing")  # pyright: ignore[reportArgumentType]

    assert "not a problem type" in reply
    assert state.record.problem_type is None


async def test_confirm_booking_incomplete_replies_missing_and_keeps_running() -> None:
    session = FakeSession(object())
    ctx = _ctx(session, BookingState())

    reply = await tools.confirm_booking(ctx)

    assert reply.startswith("Still missing:")
    assert (session.said, session.shutdowns) == ([], [])


async def test_f_1_confirm_booking_says_goodbye_and_schedules_a_draining_shutdown() -> None:
    state = BookingState()
    for field, value in (
        ("name", "Jon"),
        ("phone", "415 555 0134"),
        ("address", "27 Wattle Street, Austin, TX"),
        ("problem_type", ProblemType.PLUMBING.value),
        ("slot_id", "ST_20261110_1400"),
    ):
        state.record.set_field(field, value)  # pyright: ignore[reportArgumentType]
    session = FakeSession(object())

    reply = await tools.confirm_booking(_ctx(session, state))

    assert reply == "Confirmed."
    assert state.record.confirmed is True
    assert (session.said, session.shutdowns) == ([GOODBYE], [True])


def test_u_26_tool_names_and_args_match_schemas() -> None:
    by_name = {tool.info.name: tool for tool in tools.ALL_TOOLS}

    for schema in TOOL_SCHEMAS:
        assert schema.name in by_name
        built = llm_utils.build_legacy_openai_schema(by_name[schema.name])
        assert set(built["function"]["parameters"]["properties"]) == {arg.name for arg in schema.args}


def test_check_slots_description_states_the_iso_date_format() -> None:
    assert "YYYY-MM-DD" in (tools.check_slots.info.description or "")


def test_problem_tool_enum_matches_the_problem_types() -> None:
    built = llm_utils.build_legacy_openai_schema(tools.record_problem)

    enum = built["function"]["parameters"]["properties"]["problem_type"]["enum"]
    assert set(enum) == {t.value for t in ProblemType}
