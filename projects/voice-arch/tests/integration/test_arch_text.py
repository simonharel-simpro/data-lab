"""Live text-mode sessions (OpenRouter LLM, no audio): each architecture books a scripted caller. Costs cents."""

import asyncio
from pathlib import Path

import pytest
from livekit.agents import AgentSession

from datalab.project import repo_root
from voice_arch.agents.arch_b import StepTask
from voice_arch.agents.registry import build_agent
from voice_arch.agents.state import BookingState
from voice_arch.arch import Arch
from voice_arch.audio import make_agent_llm
from voice_arch.booking.record import SCORED_FIELDS, ExpectedRecord, is_exact
from voice_arch.settings import VoiceSettings
from voice_arch.worker_logic import MAX_TOOL_STEPS

pytestmark = pytest.mark.integration

PROJECT_DIR = Path(__file__).resolve().parents[2]
TURN_TIMEOUT_S = 120
MAX_EXTRA_YES = 3

# The scripted caller's truth and its turns: test-only values (the plan's U-2/U-4/U-8 example caller).
EXPECTED = ExpectedRecord(
    name="jon oneil",
    phone="4155550134",
    address="27 wattle st austin tx",
    problem_type="plumbing",
    slot_id="ST_20261110_1400",
)
TURNS = [
    "Hi, my name is Jon O'Neil.",
    "My phone number is 415 555 0134.",
    "The address is 27 Wattle Street, Austin, Texas 73301.",
    "My kitchen sink is leaking, so it's a plumbing problem.",
    "Tuesday afternoon would be best.",
    "Yes, the 2 PM slot please.",
]
SLOT_CHANGE = "Actually, can we do Thursday at 2 PM instead?"
YES = "Yes, that's all correct."


@pytest.fixture
def live() -> VoiceSettings:
    # Pydantic-settings kwarg.
    return VoiceSettings(_env_file=(repo_root() / ".env", PROJECT_DIR / ".env"))  # pyright: ignore[reportCallIssue]  # _env_file is a pydantic-settings init kwarg the type stub omits


async def _until_first_question(session: AgentSession[BookingState], arch: Arch) -> None:
    """B and C greet, then enter the name task: the caller's first turn must not race that hand-off."""
    if arch is Arch.A:
        return
    for _ in range(TURN_TIMEOUT_S * 10):
        if isinstance(session.current_agent, StepTask):
            return
        await asyncio.sleep(0.1)
    raise TimeoutError("the task group never reached its first task")


async def _book(live: VoiceSettings, arch: Arch, turns: list[str]) -> BookingState:
    state = BookingState()
    session = AgentSession[BookingState](llm=make_agent_llm(live), userdata=state, max_tool_steps=MAX_TOOL_STEPS)
    try:
        await session.start(build_agent(arch))
        await _until_first_question(session, arch)
        for turn in [*turns, *[YES] * MAX_EXTRA_YES]:
            if state.record.confirmed:
                break
            await asyncio.wait_for(session.run(user_input=turn), TURN_TIMEOUT_S)
    finally:
        await session.aclose()
    return state


@pytest.mark.parametrize("arch", list(Arch), ids=lambda arch: arch.value)
async def test_arch_books_a_clean_caller(live: VoiceSettings, arch: Arch) -> None:
    state = await _book(live, arch, TURNS)

    assert is_exact(state.record, EXPECTED) == (True, dict.fromkeys(SCORED_FIELDS, True))


@pytest.mark.parametrize("arch", list(Arch), ids=lambda arch: arch.value)
async def test_u_18_slot_change_during_readback_reconfirms_new_slot(live: VoiceSettings, arch: Arch) -> None:
    state = await _book(live, arch, [*TURNS, SLOT_CHANGE])

    assert (state.record.slot_id, state.record.confirmed) == ("ST_20261112_1400", True)
    assert state.taken == {"ST_20261112_1400"}
