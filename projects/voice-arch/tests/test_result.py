from types import SimpleNamespace

import pytest

from voice_arch.arch import Arch
from voice_arch.booking.record import BookingRecord, ProblemType
from voice_arch.result import CallResult, ResultFormatError, http_status_of


def test_result_round_trips() -> None:
    result = CallResult(
        room="r1",
        arch=Arch.B,
        run_id="run-7",
        record=BookingRecord(name="Jon", problem_type=ProblemType.HVAC, corrections=["name"], confirmed=True),
        report={"events": [{"type": "x", "n": 1}], "duration": 2.5},
        close_reason="user_initiated",
        error=None,
        http_status=None,
        session_errors=2,
        summarize_chat_ctx=False,
        max_tool_steps=6,
    )

    assert CallResult.from_json(result.to_json()) == result


def test_f_3_garbage_result_raises_format_error() -> None:
    with pytest.raises(ResultFormatError):
        CallResult.from_json("{not json")


def test_result_with_wrong_shape_raises_format_error() -> None:
    with pytest.raises(ResultFormatError):
        CallResult.from_json('{"arch": "z", "room": "r"}')


def test_http_status_of_finds_nested_status() -> None:
    wrapper = SimpleNamespace(error=SimpleNamespace(status_code=402))

    assert http_status_of(wrapper) == 402
    assert http_status_of(Exception("boom")) is None


def test_http_status_of_walks_the_cause_chain() -> None:
    class RateLimitedError(Exception):
        status_code = 429

    try:
        raise RuntimeError("wrapped") from RateLimitedError()
    except RuntimeError as outer:
        assert http_status_of(outer) == 429


def test_http_status_of_none_is_none() -> None:
    assert http_status_of(None) is None
