import json

import pytest
from livekit.agents.llm import LLMError
from livekit.agents.voice.events import CloseEvent, CloseReason, ErrorEvent

from voice_arch.agents.state import BookingState
from voice_arch.arch import Arch, UnknownArchError
from voice_arch.result import CallResult
from voice_arch.worker_logic import (
    MAX_TOOL_STEPS,
    TURN_HANDLING,
    CallIdentity,
    SessionOutcome,
    SessionWatch,
    build_result,
    error_result,
    parse_metadata,
)


def _close(reason: CloseReason = CloseReason.USER_INITIATED, error: LLMError | None = None) -> CloseEvent:
    return CloseEvent(reason=reason, error=error)


def _identity(room: str = "r", arch: Arch = Arch.A, run_id: str = "x") -> CallIdentity:
    return CallIdentity(room, arch, run_id)


def _outcome(
    state: BookingState | None = None,
    *,
    close: CloseEvent | None = None,
    errors: int = 0,
    summarize_chat_ctx: bool | None = None,
) -> SessionOutcome:
    return SessionOutcome(state or BookingState(), close, errors, summarize_chat_ctx, max_tool_steps=6)


def _report() -> dict[str, object]:
    return {"events": []}


def test_f_16_turn_handling_and_tool_steps_are_pinned() -> None:
    assert TURN_HANDLING == {
        "turn_detection": "vad",
        "interruption": {"mode": "vad"},
        "preemptive_generation": {"enabled": False},  # ESC-3-2: the live-call stall
    }
    assert MAX_TOOL_STEPS == 6

    result = build_result(_identity(), _outcome(), _report)

    assert CallResult.from_json(result.to_json()).max_tool_steps == 6


@pytest.mark.parametrize("raw", ['{"run_id":"r"}', "", "{x", "[]", '{"arch":"B"}', '{"arch":5}'])
def test_parse_metadata_requires_arch(raw: str) -> None:
    with pytest.raises(UnknownArchError):
        parse_metadata(raw)


def test_parse_metadata_defaults_run_id_to_manual() -> None:
    assert parse_metadata('{"arch":"b"}') == (Arch.B, "manual")


def test_parse_metadata_reads_run_id() -> None:
    assert parse_metadata(json.dumps({"arch": "c", "run_id": "run-3"})) == (Arch.C, "run-3")


def test_parse_metadata_rejects_non_string_run_id() -> None:
    with pytest.raises(UnknownArchError):
        parse_metadata('{"arch":"a","run_id":7}')


def test_f_3_report_failure_yields_error_result() -> None:
    state = BookingState()
    state.record.set_field("name", "Jon")

    def failing() -> dict[str, object]:
        raise RuntimeError("recorder still recording")

    result = build_result(_identity(arch=Arch.B), _outcome(state, summarize_chat_ctx=False, close=_close()), failing)

    assert result.report is None
    assert result.error is not None
    assert "recorder still recording" in result.error
    assert result.record is not None
    assert result.record.name == "Jon"


def test_f_15_build_result_carries_the_summarize_flag() -> None:
    result = build_result(_identity(arch=Arch.B), _outcome(summarize_chat_ctx=False), _report)

    assert result.summarize_chat_ctx is False


def test_build_result_carries_close_reason_report_and_error_count() -> None:
    result = build_result(
        _identity("room-9", Arch.C, "run-1"),
        _outcome(close=_close(CloseReason.PARTICIPANT_DISCONNECTED), errors=3),
        _report,
    )

    assert (result.room, result.arch, result.run_id) == ("room-9", Arch.C, "run-1")
    assert result.close_reason == "participant_disconnected"
    assert result.session_errors == 3
    assert result.report == {"events": []}
    assert result.error is None


def test_build_result_takes_http_status_from_the_close_error() -> None:
    class ApiError(Exception):
        status_code = 402

    failure = LLMError(timestamp=0.0, label="llm", error=ApiError("payment required"), recoverable=False)
    close = _close(CloseReason.ERROR, error=failure)

    result = build_result(_identity(), _outcome(close=close, errors=1), _report)

    assert result.http_status == 402
    assert result.error is not None
    assert "payment required" in result.error


def test_build_result_record_is_a_copy() -> None:
    state = BookingState()
    result = build_result(_identity(), _outcome(state), _report)

    state.record.set_field("name", "later")

    assert result.record is not None
    assert result.record.name is None


def test_f_9_error_result_has_no_arch_and_no_record() -> None:
    result = error_result("r", "unknown arch 'z'")

    assert (result.arch, result.record, result.report) == (None, None, None)
    assert result.error == "unknown arch 'z'"


def test_session_watch_counts_errors_and_keeps_the_last_close() -> None:
    watch = SessionWatch()

    watch.on_error(ErrorEvent(error="e1", source="s"))
    watch.on_error(ErrorEvent(error="e2", source="s"))
    watch.on_close(_close(CloseReason.ERROR))
    last = _close(CloseReason.USER_INITIATED)
    watch.on_close(last)

    assert watch.errors == 2
    assert watch.close is last
    assert watch.closed.is_set()
