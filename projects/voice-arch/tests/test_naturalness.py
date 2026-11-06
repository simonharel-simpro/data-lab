import pytest

from voice_arch.naturalness import ReportShapeError, barge_ins, latencies, long_silences, session_errors


def _msg(
    role: str,
    text: str = "x",
    *,
    start: float | None = None,
    stop: float | None = None,
    e2e: float | None = None,
    interrupted: bool = False,
) -> dict[str, object]:
    metrics: dict[str, float] = {}
    if start is not None:
        metrics["started_speaking_at"] = start
    if stop is not None:
        metrics["stopped_speaking_at"] = stop
    if e2e is not None:
        metrics["e2e_latency"] = e2e
    return {"type": "message", "role": role, "interrupted": interrupted, "content": [text], "metrics": metrics}


def _report(items: list[dict[str, object]], events: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {"chat_history": {"items": items}, "events": events or []}


def _gap_report(gap: float) -> dict[str, object]:
    base = 100.0
    return _report([_msg("user", start=base - 1, stop=base), _msg("assistant", start=base + gap, stop=base + gap + 1)])


def test_u_11_exactly_two_seconds_is_not_long() -> None:
    assert long_silences(_gap_report(2.0)) == 0
    assert long_silences(_gap_report(2.01)) == 1


def test_long_silence_skips_turns_without_timestamps() -> None:
    report = _report([_msg("user", stop=10.0), _msg("assistant")])

    assert long_silences(report) == 0


def test_u_12_verbatim_repeat_after_interrupt_is_not_handled() -> None:
    line = "Your number is 415 555 0134, is that right?"
    report = _report([_msg("assistant", line, interrupted=True), _msg("user"), _msg("assistant", line)])

    assert barge_ins(report) == (1, 0)


def test_u_12_new_reply_after_interrupt_is_handled() -> None:
    report = _report(
        [
            _msg("assistant", "Your number is 415 555 0134, is that right?", interrupted=True),
            _msg("user"),
            _msg("assistant", "Sure, the appointment is Tuesday at 2 PM."),
        ]
    )

    assert barge_ins(report) == (1, 1)


def test_interrupt_with_no_following_reply_is_not_handled() -> None:
    assert barge_ins(_report([_msg("assistant", "Hello there", interrupted=True)])) == (1, 0)


def test_no_interruptions_gives_zero_zero() -> None:
    assert barge_ins(_report([_msg("assistant", "Hello there")])) == (0, 0)


def test_latencies_has_one_entry_per_assistant_turn_with_none_for_missing() -> None:
    report = _report([_msg("assistant", e2e=1.5), _msg("user"), _msg("assistant"), _msg("assistant", e2e=0.9)])

    assert latencies(report) == [1.5, None, 0.9]


def test_f_14_session_errors_are_counted() -> None:
    events: list[dict[str, object]] = [{"type": "error"}, {"type": "agent_state_changed"}, {"type": "error"}]

    assert session_errors(_report([], events)) == 2


def test_report_without_chat_history_is_a_loud_shape_error() -> None:
    with pytest.raises(ReportShapeError, match="chat_history"):
        latencies({"events": []})
