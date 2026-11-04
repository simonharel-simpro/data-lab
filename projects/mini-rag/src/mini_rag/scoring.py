"""Answer scoring: normalized token-boundary containment, IDK = missing, `score = accuracy - hallucination` (D-7).

`normalize`, `contains_phrase`, `parse_number`, `numbers_equal` and the IDK variants are copied from Demo-RAG
(`Demo-RAG-crag-dataset/src/crag_rag/normalize.py` and `evaluation.py:20-23,72`), reused rather than re-specified (B-3).
"""

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Final

_APOSTROPHES: Final = {
    "'",
    "`",
    "\N{RIGHT SINGLE QUOTATION MARK}",
    "\N{LEFT SINGLE QUOTATION MARK}",
    "\N{MODIFIER LETTER APOSTROPHE}",
}
_ARTICLES: Final = {"a", "an", "the"}
_MULTIPLIERS: Final = {
    "k": 1e3,
    "thousand": 1e3,
    "m": 1e6,
    "mn": 1e6,
    "million": 1e6,
    "b": 1e9,
    "bn": 1e9,
    "billion": 1e9,
    "t": 1e12,
    "trillion": 1e12,
}
_NUMBER: Final = re.compile(r"^[$€£]?\s*(?P<num>-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|-?\.\d+)\s*(?P<mult>[a-z]+)?$")


class Outcome(StrEnum):
    CORRECT = "correct"
    MISSING = "missing"
    HALLUCINATION = "hallucination"


@dataclass(frozen=True)
class Metrics:
    accuracy: float
    hallucination: float
    missing: float
    score: float

    def as_dict(self, prefix: str = "") -> dict[str, float]:
        return {f"{prefix}{key}": value for key, value in asdict(self).items()}


def normalize(text: str) -> str:
    """Lowercase, NFKC, drop apostrophes, punctuation -> space, drop articles, collapse whitespace."""
    text = unicodedata.normalize("NFKC", text).lower()
    chars = []
    for ch in text:
        if ch in _APOSTROPHES:
            continue
        chars.append(" " if unicodedata.category(ch)[0] in {"P", "S"} else ch)
    return " ".join(tok for tok in "".join(chars).split() if tok not in _ARTICLES)


def contains_phrase(haystack: str, needle: str) -> bool:
    """Token-boundary containment on normalised text, so `5050` does not match `50505`."""
    return bool(needle) and f" {needle} " in f" {haystack} "


def parse_number(text: str) -> float | None:
    """Parse a whole answer as a number: `1,000,000`, `1 million`, `1.5k`, `$3.2 bn`. Otherwise None."""
    cleaned = unicodedata.normalize("NFKC", text).strip().lower().rstrip(".").strip()
    match = _NUMBER.match(cleaned)
    if match is None:
        return None
    multiplier = 1.0
    if match.group("mult") is not None:
        found = _MULTIPLIERS.get(match.group("mult"))
        if found is None:
            return None
        multiplier = found
    value = float(match.group("num").replace(",", "")) * multiplier
    return value if math.isfinite(value) else None


def numbers_equal(a: str, b: str) -> bool:
    x, y = parse_number(a), parse_number(b)
    return x is not None and y is not None and math.isclose(x, y, rel_tol=1e-9, abs_tol=1e-12)


# No bare "unknown" variant: it would turn correct answers containing the word into `missing` (B-3).
_IDK_VARIANTS: Final = (normalize("i don't know"), normalize("i do not know"))


def is_idk(prediction: str) -> bool:
    norm = normalize(prediction)
    return any(contains_phrase(norm, variant) for variant in _IDK_VARIANTS)


def outcome(pred: str, expected: str | None) -> Outcome:
    """Rules in order: IDK, unanswerable, numeric equality, normalized containment (U-12)."""
    if is_idk(pred):
        return Outcome.MISSING
    if expected is None:
        return Outcome.HALLUCINATION
    if numbers_equal(pred, expected):
        return Outcome.CORRECT
    if contains_phrase(normalize(pred), normalize(expected)):
        return Outcome.CORRECT
    return Outcome.HALLUCINATION


def metrics(outcomes: Sequence[Outcome]) -> Metrics:
    if not outcomes:
        raise ValueError("no outcome to score: a run must answer at least one question")
    counts, n = Counter(outcomes), len(outcomes)
    accuracy, hallucination = counts[Outcome.CORRECT] / n, counts[Outcome.HALLUCINATION] / n
    return Metrics(
        accuracy=accuracy,
        hallucination=hallucination,
        missing=counts[Outcome.MISSING] / n,
        score=accuracy - hallucination,
    )
