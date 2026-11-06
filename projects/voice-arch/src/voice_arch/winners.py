"""Stage-1 winner selection (U-9, U-22): accuracy first, latency among the statistically tied; cost is reported only."""

import math
from collections.abc import Sequence
from dataclasses import dataclass


class NoEligibleCandidate(Exception):
    """No candidate can win: an empty field, or every TTS candidate unintelligible."""


@dataclass(frozen=True)
class Choice:
    model: str
    reason: str


@dataclass(frozen=True)
class SttRow:
    model: str
    errors: int
    n_utterances: int
    p50_s: float


@dataclass(frozen=True)
class TtsRow:
    model: str
    ttfb_p50_s: float
    intelligible: bool


@dataclass(frozen=True)
class LlmRow:
    model: str
    correct: int
    n_cases: int
    ttft_p50_s: float


def pick_stt(rows: Sequence[SttRow]) -> Choice:
    """Candidates within `ceil(n / 40)` errors of the best (margin measured from the best) tie: lowest p50 wins."""
    if not rows:
        raise NoEligibleCandidate("no STT candidate")
    best = min(r.errors for r in rows)
    margin = math.ceil(max(r.n_utterances for r in rows) / 40)
    tied = [r for r in rows if r.errors <= best + margin]
    winner = min(tied, key=lambda r: (r.p50_s, r.errors, r.model))
    return Choice(
        winner.model,
        f"{winner.errors} errors (best {best}, margin {margin}), p50 {winner.p50_s:.2f} s among {len(tied)} tied",
    )


def pick_tts(rows: Sequence[TtsRow]) -> Choice:
    eligible = [r for r in rows if r.intelligible]
    if not eligible:
        raise NoEligibleCandidate("no intelligible TTS candidate")
    winner = min(eligible, key=lambda r: (r.ttfb_p50_s, r.model))
    return Choice(winner.model, f"intelligible, lowest TTFB p50 {winner.ttfb_p50_s:.2f} s of {len(eligible)}")


def pick_llm(rows: Sequence[LlmRow]) -> Choice:
    if not rows:
        raise NoEligibleCandidate("no LLM candidate")
    best = max(r.correct for r in rows)
    winner = min((r for r in rows if r.correct == best), key=lambda r: (r.ttft_p50_s, r.model))
    return Choice(winner.model, f"{winner.correct}/{winner.n_cases} correct, TTFT p50 {winner.ttft_p50_s:.2f} s")
