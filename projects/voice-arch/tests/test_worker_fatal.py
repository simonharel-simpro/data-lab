"""ESC-3-1 / sweep prerequisite: an unrecoverable LLM error ends the call at once, scored by its record."""

import pytest
from livekit.agents import AgentSession
from livekit.agents.llm import LLMError
from livekit.agents.stt import STTError
from livekit.agents.voice.events import CloseEvent, CloseReason, ErrorEvent

from voice_arch.agents.state import BookingState
from voice_arch.arch import Arch
from voice_arch.result import CallResult
from voice_arch.worker_logic import SessionWatch, build_result


class ProviderError(Exception):
    status_code = 502


class FakeSession:
    """Only what `SessionWatch` touches: `on` (a registry) and `shutdown` (a recorder)."""

    def __init__(self) -> None:
        self.handlers: dict[str, object] = {}
        self.shutdowns: list[bool] = []

    def on(self, event: str, callback: object) -> None:
        self.handlers[event] = callback

    def shutdown(self, *, drain: bool) -> None:
        self.shutdowns.append(drain)


def _llm_error(*, recoverable: bool) -> ErrorEvent:
    failure = LLMError(timestamp=0.0, label="llm", error=ProviderError("bad gateway"), recoverable=recoverable)
    return ErrorEvent(error=failure, source=object())


def _watch(session: FakeSession) -> SessionWatch:
    watch = SessionWatch()
    watch.attach(session)  # pyright: ignore[reportArgumentType]
    return watch


def _result(watch: SessionWatch) -> CallResult:
    return build_result(
        "r", Arch.C, "x", BookingState(), watch.close, watch.errors, lambda: {}, summarize_chat_ctx=False,
        max_tool_steps=6, fatal=watch.fatal,
    )  # fmt: skip


def test_unrecoverable_llm_error_shuts_the_session_down_without_draining() -> None:
    session = FakeSession()
    watch = _watch(session)

    watch.on_error(_llm_error(recoverable=False))

    assert session.shutdowns == [False]  # drain=False: nothing is left to say, and the agent is silent anyway
    assert watch.errors == 1
    assert watch.fatal is not None


def test_recoverable_llm_error_does_not_end_the_session() -> None:
    session = FakeSession()
    watch = _watch(session)

    watch.on_error(_llm_error(recoverable=True))

    assert session.shutdowns == []
    assert watch.fatal is None
    assert watch.errors == 1


def test_unrecoverable_error_of_another_component_is_left_to_livekit() -> None:
    session = FakeSession()
    watch = _watch(session)
    stt_failure = STTError(timestamp=0.0, label="stt", error=ProviderError("x"), recoverable=False)

    watch.on_error(ErrorEvent(error=stt_failure, source=object()))

    assert session.shutdowns == []
    assert watch.fatal is None


def test_result_of_a_fatal_llm_error_carries_the_error_status_and_reason() -> None:
    watch = _watch(FakeSession())
    watch.on_error(_llm_error(recoverable=False))
    watch.on_close(CloseEvent(reason=CloseReason.USER_INITIATED, error=None))

    result = _result(watch)

    assert result.close_reason == CloseReason.ERROR.value
    assert result.http_status == 502
    assert "unrecoverable LLM error" in (result.error or "")
    assert "bad gateway" in (result.error or "")


def test_result_without_a_fatal_error_is_unchanged() -> None:
    watch = _watch(FakeSession())
    watch.on_close(CloseEvent(reason=CloseReason.USER_INITIATED, error=None))

    result = _result(watch)

    assert (result.close_reason, result.error, result.http_status) == ("user_initiated", None, None)


async def test_attach_registers_the_handler_on_a_real_session(monkeypatch: pytest.MonkeyPatch) -> None:
    session = AgentSession[BookingState]()
    shutdowns: list[bool] = []
    monkeypatch.setattr(session, "shutdown", lambda *, drain=True: shutdowns.append(drain))
    watch = SessionWatch()
    watch.attach(session)

    session.emit("error", _llm_error(recoverable=False))

    assert shutdowns == [False]
    assert watch.fatal is not None
