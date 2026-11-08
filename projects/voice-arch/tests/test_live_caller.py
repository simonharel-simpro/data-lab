"""The pure parts of the live caller's bookkeeping, driven with stand-ins for the room and the session."""

# pyright: reportPrivateUsage=false

from types import SimpleNamespace
from typing import cast

import pytest
from livekit import rtc
from livekit.agents import AgentSession
from livekit.agents.voice.events import CloseEvent, CloseReason, ErrorEvent

from voice_arch import live_caller
from voice_arch.live_caller import LiveCaller


class Gate:
    def __init__(self) -> None:
        self.calls: list[bool] = []

    def set_audio_enabled(self, enabled: bool) -> None:
        self.calls.append(enabled)


def _caller(listen_after: int) -> tuple[LiveCaller, Gate]:
    gate = Gate()
    room = SimpleNamespace(
        register_text_stream_handler=lambda topic, handler: None, on=lambda event, callback: callback
    )
    session = SimpleNamespace(on=lambda event, callback: callback, input=gate)
    caller = LiveCaller(cast("rtc.Room", room), cast("AgentSession[None]", session), listen_after)
    caller._started = True  # the session start is not under test
    return caller, gate


def _error(**fields: object) -> ErrorEvent:
    return cast("ErrorEvent", SimpleNamespace(**fields))


def test_b_and_c_caller_is_deaf_until_the_greeting_has_ended() -> None:
    caller, gate = _caller(listen_after=1)

    caller._apply_gate()
    caller._on_agent_state("speaking")
    heard_during_greeting = list(gate.calls)
    caller._on_agent_state("thinking")

    assert heard_during_greeting == [False]
    assert gate.calls == [False, True]


def test_a_caller_listens_from_the_start() -> None:
    caller, gate = _caller(listen_after=0)

    caller._apply_gate()
    caller._on_agent_state("speaking")
    caller._on_agent_state("listening")

    assert gate.calls == []


def test_agent_speaking_for_counts_from_the_start_of_the_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    caller, _ = _caller(listen_after=0)
    start, now = 100.0, 101.5
    clock = iter([start, now])
    monkeypatch.setattr(live_caller.time, "monotonic", lambda: next(clock))
    assert caller.agent_speaking_for() == 0.0

    caller._on_agent_state("speaking")

    assert caller.agent_speaking_for() == pytest.approx(now - start)


def test_recoverable_error_keeps_the_http_status_but_is_not_a_fault() -> None:
    caller, _ = _caller(listen_after=0)
    status = 429

    caller._on_error(_error(error=SimpleNamespace(recoverable=True, status_code=status)))

    assert (caller.caller_http_status, caller.caller_error) == (status, None)


def test_unrecoverable_error_is_a_fault_that_never_echoes_the_message() -> None:
    caller, _ = _caller(listen_after=0)
    secret = "sk-or-not-for-the-log"
    inner = RuntimeError(secret)

    caller._on_error(_error(error=SimpleNamespace(recoverable=False, status_code=500, error=inner)))

    assert caller.caller_error == "RuntimeError (HTTP 500)"
    assert secret not in str(caller.caller_error)


def test_normal_close_is_not_an_error_but_an_error_close_is() -> None:
    caller, _ = _caller(listen_after=0)
    normal = cast("CloseEvent", SimpleNamespace(error=None, reason=CloseReason.PARTICIPANT_DISCONNECTED))
    failed = cast("CloseEvent", SimpleNamespace(error=None, reason=CloseReason.ERROR))

    caller._on_close(normal)
    assert caller.caller_error is None
    caller._on_close(failed)

    assert caller.caller_error == "session closed on error"


async def test_wait_agent_times_out_when_no_agent_joins() -> None:
    caller, _ = _caller(listen_after=0)

    assert await caller.wait_agent(0.05) is False


async def test_wait_result_is_none_without_a_result() -> None:
    caller, _ = _caller(listen_after=0)

    assert await caller.wait_result(0.05) is None


class _Session:
    def __init__(self, error: Exception | None = None) -> None:
        self.said: list[str] = []
        self._error = error

    def say(self, text: str, *, allow_interruptions: bool) -> None:
        if self._error is not None:
            raise self._error
        self.said.append(text)


def _with_session(session: _Session, *, started: bool) -> LiveCaller:
    caller, _ = _caller(listen_after=0)
    caller._session = cast("AgentSession[None]", session)
    caller._started = started
    return caller


async def test_interject_on_unstarted_caller_does_not_say() -> None:
    session = _Session(RuntimeError("AgentSession isn't running"))
    caller = _with_session(session, started=False)

    await caller.interject("wait, actually")

    assert session.said == []


async def test_interject_that_raises_runtime_error_sets_caller_error() -> None:
    caller = _with_session(_Session(RuntimeError("AgentSession is closing, cannot use say()")), started=True)

    await caller.interject("wait, actually")

    assert caller.caller_error == "interjection failed: RuntimeError"


async def test_interject_on_started_caller_says_the_text() -> None:
    session = _Session()
    caller = _with_session(session, started=True)

    await caller.interject("wait, actually")

    assert session.said == ["wait, actually"]
