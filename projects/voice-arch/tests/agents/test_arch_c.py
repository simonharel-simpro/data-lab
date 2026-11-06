from types import SimpleNamespace
from typing import cast

from livekit.agents import RunContext

from voice_arch.agents.arch_b import SlotTask
from voice_arch.agents.arch_c import read_record, update_record
from voice_arch.agents.state import BookingState


def _ctx(current_agent: object, state: BookingState) -> RunContext[BookingState]:
    session = SimpleNamespace(current_agent=current_agent)
    return cast("RunContext[BookingState]", SimpleNamespace(session=session, userdata=state))


async def test_update_record_sets_a_field_and_never_completes_the_task() -> None:
    state, task = BookingState(), SlotTask()

    reply = await update_record(_ctx(task, state), "phone", "415 555 0134")

    assert reply == "Noted."
    assert state.record.phone == "415 555 0134"
    assert task.done() is False


async def test_update_record_unknown_field_returns_error_text() -> None:
    state = BookingState()

    reply = await update_record(_ctx(object(), state), "confirmed", "true")

    assert "Unknown field" in reply
    assert state.record.confirmed is False


async def test_update_record_slot_obeys_availability_rules() -> None:
    state = BookingState()

    refused = await update_record(_ctx(object(), state), "slot_id", "ST_20261109_0900")
    accepted = await update_record(_ctx(object(), state), "slot_id", "ST_20261110_1400")

    assert "taken" in refused
    assert accepted.startswith("Chosen")
    assert (state.record.slot_id, state.taken) == ("ST_20261110_1400", {"ST_20261110_1400"})


async def test_read_record_lists_filled_and_missing_fields() -> None:
    state = BookingState()
    state.record.set_field("name", "Jon")

    text = await read_record(_ctx(object(), state))

    assert "name: Jon" in text
    assert "Missing: phone, address, problem_type, slot_id" in text
