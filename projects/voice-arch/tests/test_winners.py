import pytest

from voice_arch.winners import (
    LlmRow,
    NoEligibleCandidate,
    SttRow,
    TtsRow,
    pick_llm,
    pick_stt,
    pick_tts,
)


def _stt(model: str, errors: int, p50_s: float, n: int = 40) -> SttRow:
    return SttRow(model=model, errors=errors, n_utterances=n, p50_s=p50_s)


def test_u_9_accuracy_within_margin_falls_back_to_latency() -> None:
    choice = pick_stt([_stt("A", 2, 0.6), _stt("B", 1, 1.1)])

    assert choice.model == "A"


def test_pick_stt_outside_margin_prefers_accuracy() -> None:
    choice = pick_stt([_stt("A", 4, 0.6), _stt("B", 1, 1.1)])

    assert choice.model == "B"


def test_u_22_stt_margin_is_measured_from_the_best() -> None:
    choice = pick_stt([_stt("A", 1, 1.0), _stt("B", 2, 0.9), _stt("C", 3, 0.5)])

    assert choice.model == "B"


def test_pick_stt_margin_scales_with_corpus_size() -> None:
    # ceil(41 / 40) = 2: a candidate 2 errors behind the best still ties.
    assert pick_stt([_stt("A", 3, 0.5, 41), _stt("B", 1, 1.0, 41)]).model == "A"


def test_pick_stt_with_no_rows_raises() -> None:
    with pytest.raises(NoEligibleCandidate):
        pick_stt([])


def test_u_22_pick_tts_with_no_intelligible_candidate_raises() -> None:
    rows = [TtsRow("A", 0.3, False), TtsRow("B", 0.2, False)]

    with pytest.raises(NoEligibleCandidate):
        pick_tts(rows)


def test_pick_tts_ignores_unintelligible_fast_candidate() -> None:
    choice = pick_tts([TtsRow("fast", 0.1, False), TtsRow("ok", 0.4, True), TtsRow("slow", 0.9, True)])

    assert choice.model == "ok"


def test_pick_llm_accuracy_then_ttft() -> None:
    choice = pick_llm([LlmRow("A", 19, 20, 0.9), LlmRow("B", 20, 20, 1.2)])

    assert choice.model == "B"


def test_pick_llm_tie_on_correct_takes_lowest_ttft() -> None:
    choice = pick_llm([LlmRow("A", 20, 20, 1.2), LlmRow("B", 20, 20, 0.9)])

    assert choice.model == "B"
    assert choice.reason
