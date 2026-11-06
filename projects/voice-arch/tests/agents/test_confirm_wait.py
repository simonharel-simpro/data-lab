"""`confirm_booking` waits for the caller's answer to the read-back (live B call: read-back and confirm in one turn)."""

import time
from types import SimpleNamespace
from typing import cast

from livekit.agents import RunContext
from livekit.agents.llm import ChatContext

from voice_arch.agents import tools
from voice_arch.agents.arch_c import update_record
from voice_arch.agents.state import BookingState
from voice_arch.booking.actions import WAIT_FOR_CALLER
from voice_arch.booking.instructions import GOODBYE


class FakeSession:
    def __init__(self, history: ChatContext) -> None:
        self.current_agent = object()
        self.history = history
        self.said: list[str] = []
        self.shutdowns: list[bool] = []

    def say(self, text: str) -> None:
        self.said.append(text)

    def shutdown(self, *, drain: bool) -> None:
        self.shutdowns.append(drain)


def _ctx(session: FakeSession, state: BookingState) -> RunContext[BookingState]:
    return cast("RunContext[BookingState]", SimpleNamespace(session=session, userdata=state))


def _history(*messages: tuple[str, float]) -> ChatContext:
    history = ChatContext()
    for role, created_at in messages:
        history.add_message(role=role, content="text", created_at=created_at)  # pyright: ignore[reportArgumentType]
    return history


async def _fill(ctx: RunContext[BookingState]) -> None:
    await tools.record_name(ctx, "Jon")
    await tools.record_phone(ctx, "415 555 0134")
    await tools.record_address(ctx, "27 Wattle Street, Austin, TX")
    await tools.record_problem(ctx, "plumbing")
    await tools.choose_slot(ctx, "ST_20261110_1400")


async def test_confirm_in_the_turn_of_the_last_write_is_refused() -> None:
    now = time.time()
    session, state = FakeSession(_history(("user", now - 5))), BookingState()
    ctx = _ctx(session, state)
    await _fill(ctx)  # every write is after the caller's last message

    reply = await tools.confirm_booking(ctx)

    assert reply == WAIT_FOR_CALLER
    assert state.record.confirmed is False
    assert (session.said, session.shutdowns) == ([], [])


async def test_confirm_after_the_callers_yes_succeeds() -> None:
    session, state = FakeSession(ChatContext()), BookingState()
    ctx = _ctx(session, state)
    await _fill(ctx)
    session.history.add_message(role="user", content="Yes", created_at=time.time() + 1)

    reply = await tools.confirm_booking(ctx)

    assert reply == "Confirmed."
    assert state.record.confirmed is True
    assert (session.said, session.shutdowns) == ([GOODBYE], [True])


async def test_a_correction_after_the_yes_needs_a_new_yes() -> None:
    session, state = FakeSession(ChatContext()), BookingState()
    ctx = _ctx(session, state)
    await _fill(ctx)
    session.history.add_message(role="user", content="No, the phone is 415 555 0199", created_at=time.time() + 1)
    state.last_write_at = time.time() + 2  # the agent's correction of the phone lands after the caller's message

    refused = await tools.confirm_booking(ctx)
    session.history.add_message(role="user", content="Yes", created_at=time.time() + 3)
    confirmed = await tools.confirm_booking(ctx)

    assert (refused, confirmed) == (WAIT_FOR_CALLER, "Confirmed.")


async def test_assistant_messages_do_not_count_as_the_callers_answer() -> None:
    session, state = FakeSession(ChatContext()), BookingState()
    ctx = _ctx(session, state)
    await _fill(ctx)
    session.history.add_message(role="assistant", content="Is that correct?", created_at=time.time() + 1)

    assert await tools.confirm_booking(ctx) == WAIT_FOR_CALLER


async def test_update_record_under_c_also_starts_the_wait() -> None:
    session, state = FakeSession(ChatContext()), BookingState()
    ctx = _ctx(session, state)
    await _fill(ctx)
    session.history.add_message(role="user", content="Yes", created_at=time.time() + 1)
    state.last_write_at = None  # as if the caller's yes had already been given

    await update_record(ctx, "phone", "415 555 0199")

    assert state.last_write_at is not None
    session.history.items.clear()  # the correction came after the only user message
    assert await tools.confirm_booking(ctx) == WAIT_FOR_CALLER


async def test_failed_write_does_not_start_the_wait() -> None:
    state = BookingState()
    ctx = _ctx(FakeSession(ChatContext()), state)

    await tools.record_problem(ctx, "roofing")  # pyright: ignore[reportArgumentType]

    assert state.last_write_at is None
