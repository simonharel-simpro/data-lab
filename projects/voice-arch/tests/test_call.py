import asyncio
import logging

import pytest
from livekit.agents import Agent

from tests.call_fakes import FakeEnv, FakeHandle, persona, result_for
from voice_arch import call
from voice_arch.arch import Arch
from voice_arch.booking.record import SCORED_FIELDS
from voice_arch.call import AgentNeverJoined, CallRow, LiveKitUnresponsive, Outcome, ProviderAuthStop, run_one_call
from voice_arch.call_env import CallerHandle
from voice_arch.caller import CallerAgent
from voice_arch.personas import Persona

TIMEOUT_S = 0.1
JOIN_S = 1.0


async def _call(env: FakeEnv, who_id: str = "self_correction", timeout: float = TIMEOUT_S) -> CallRow:
    return await run_one_call(
        env, persona(who_id), Arch.A, "0123456789abcdef", 0, call_timeout_s=timeout, join_timeout_s=JOIN_S
    )


async def test_f_1_runner_times_out_a_call_whose_caller_never_hangs_up() -> None:
    handle = FakeHandle(result=None)
    env = FakeEnv([handle])

    outcome = await _call(env)

    assert outcome.outcome is Outcome.TIMEOUT
    assert env.deleted == env.rooms
    assert handle.closed


async def test_f_2_agent_never_joins_raises() -> None:
    handle = FakeHandle(joins=False)
    env = FakeEnv([handle])

    with pytest.raises(AgentNeverJoined):
        await _call(env)

    assert env.deleted == env.rooms
    assert handle.closed


async def test_f_3_missing_result_scores_as_failure() -> None:
    env = FakeEnv([FakeHandle(result=None, agent_left=True)])

    row = await _call(env)

    assert row.outcome is Outcome.AGENT_LOST
    assert row.exact is False
    assert row.per_field == dict.fromkeys(SCORED_FIELDS, False)


async def test_f_4_402_raises_before_caller_fault() -> None:
    who = persona()
    env = FakeEnv([FakeHandle(result_for(who, http_status=402), caller_error="tts 402")])

    with pytest.raises(ProviderAuthStop):
        await _call(env)

    assert env.deleted == env.rooms


async def test_caller_side_402_stops_the_sweep() -> None:
    env = FakeEnv([FakeHandle(result=None, caller_http_status=402)])

    with pytest.raises(ProviderAuthStop):
        await _call(env)


async def test_f_4_401_also_stops_the_sweep() -> None:
    env = FakeEnv([FakeHandle(result_for(persona(), http_status=401))])

    with pytest.raises(ProviderAuthStop):
        await _call(env)


async def test_f_6_caller_error_close_is_classified_caller_fault() -> None:
    env = FakeEnv([FakeHandle(result_for(persona()), caller_error="tts 500")])

    row = await _call(env)

    assert row.outcome is Outcome.CALLER_FAULT


async def test_normal_close_after_result_is_scored() -> None:
    who = persona()
    env = FakeEnv([FakeHandle(result_for(who), agent_left=True, caller_error=None)])

    row = await _call(env)

    assert row.outcome is Outcome.SCORED
    assert row.exact is True
    assert all(row.per_field.values())


async def test_scored_row_carries_report_counters() -> None:
    who = persona()
    user = {
        "type": "message",
        "role": "user",
        "interrupted": False,
        "content": ["hi"],
        "metrics": {"started_speaking_at": 1.0, "stopped_speaking_at": 10.0},
    }
    assistant = {"type": "message", "role": "assistant", "interrupted": False, "content": ["Hello"],
                 "metrics": {"started_speaking_at": 13.0, "stopped_speaking_at": 14.0, "e2e_latency": 3.0}}  # fmt: skip
    report: dict[str, object] = {"chat_history": {"items": [user, assistant]}, "events": [{"type": "error"}]}
    env = FakeEnv([FakeHandle(result_for(who, report=report))])

    row = await _call(env)

    assert (row.latencies, row.agent_turns) == ([3.0], 1)
    assert (row.long_silences, row.session_errors) == (1, 1)


async def test_interrupter_fires_interjections_while_agent_speaks() -> None:
    who = persona("interrupter")
    handle = FakeHandle(result_for(who), speaking_for=1.2, result_after=4)
    env = FakeEnv([handle])

    await _call(env, "interrupter", timeout=5.0)

    assert handle.interjected == list(who.interjections)


async def test_no_interjection_before_the_agent_has_spoken_a_second() -> None:
    who = persona("interrupter")
    handle = FakeHandle(result_for(who), speaking_for=0.5, result_after=3)
    env = FakeEnv([handle])

    await _call(env, "interrupter", timeout=5.0)

    assert handle.interjected == []


def test_f_8_caller_does_not_speak_before_first_agent_turn() -> None:
    who = persona()

    agent = CallerAgent(who.instructions)

    assert CallerAgent.on_enter is Agent.on_enter
    assert "Never speak first." in agent.instructions
    assert who.instructions in agent.instructions


class _HangingEnv(FakeEnv):
    def __init__(self, hang: str, handles: list[FakeHandle] | None = None) -> None:
        super().__init__(handles or [])
        self._hang = hang

    async def create_dispatch(self, room: str, arch: Arch, run_id: str) -> None:
        if self._hang == "create_dispatch":
            await asyncio.Event().wait()
        await super().create_dispatch(room, arch, run_id)

    async def connect_caller(self, room: str, who: Persona, arch: Arch) -> CallerHandle:
        if self._hang == "connect_caller":
            await asyncio.Event().wait()
        return await super().connect_caller(room, who, arch)


class _HangingCloseHandle(FakeHandle):
    async def close(self) -> None:
        await asyncio.Event().wait()


@pytest.mark.parametrize("step", ["create_dispatch", "connect_caller"])
async def test_run_one_call_bounds_a_step_that_never_returns(step: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(call, "STEP_TIMEOUT_S", 0.05)
    env = _HangingEnv(step)

    with pytest.raises(LiveKitUnresponsive, match=step):
        await _call(env)

    assert len(env.deleted) == 1  # _cleanup still ran


async def test_cleanup_bounds_a_close_that_never_returns(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(call, "STEP_TIMEOUT_S", 0.05)
    env = FakeEnv([_HangingCloseHandle(result_for(persona()))])

    with caplog.at_level(logging.WARNING):
        row = await asyncio.wait_for(_call(env), 1.0)

    assert row.outcome is Outcome.SCORED
    assert env.deleted == env.rooms
    assert any(r.levelno == logging.WARNING for r in caplog.records)


async def test_interject_on_unstarted_caller_yields_caller_fault_row() -> None:
    handle = FakeHandle(result=None, caller_error="caller session failed to start: RuntimeError", speaking_for=1.2)
    env = FakeEnv([handle])

    row = await _call(env, "interrupter", timeout=0.3)

    assert row.outcome is Outcome.CALLER_FAULT
