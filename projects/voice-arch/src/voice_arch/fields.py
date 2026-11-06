"""Field-level scoring shared by the STT bench (transcript vs truth) and the LLM bench (tool args vs expected)."""

from collections.abc import Callable, Mapping

from voice_arch.booking.normalize import (
    contains_phrase,
    normalize_address,
    normalize_name,
    normalize_phone,
    normalize_text,
    spoken_digits,
)

_EXACT_FIELDS = frozenset({"problem_type", "slot_id"})
_NORMALISERS: dict[str, Callable[[str], str]] = {
    "name": normalize_name,
    "phone": normalize_phone,
    "address": normalize_address,
}


def _transcript_error(field: str, transcript: str, truth: str) -> bool:
    if field == "phone":
        needle = normalize_phone(truth)
        return not needle or needle not in spoken_digits(transcript)
    # "slot" has no dedicated normaliser: plain text containment.
    normaliser = _NORMALISERS.get(field, normalize_text)
    # normalize_text last: a transcript says "Maria Garcia, that's ...", the comma must not hide the name.
    return not contains_phrase(normalize_text(normaliser(transcript)), normalize_text(normaliser(truth)))


def field_errors(transcript: str, truth: Mapping[str, str]) -> dict[str, bool]:
    """True = the field is wrong in the transcript. An empty transcript errs on every field (F-10)."""
    return {field: _transcript_error(field, transcript, value) for field, value in truth.items()}


def _arg_equal(field: str, actual: str, expected: str) -> bool:
    if field in _EXACT_FIELDS:
        return actual == expected
    normaliser = _NORMALISERS.get(field, normalize_text)
    return normaliser(actual) == normaliser(expected)


def args_correct(actual: Mapping[str, object], expected: Mapping[str, str]) -> bool:
    """Same keys, each value equal after its field's normaliser; `problem_type` / `slot_id` exact (U-15)."""
    if set(actual) != set(expected):
        return False
    return all(isinstance(actual[k], str) and _arg_equal(k, str(actual[k]), v) for k, v in expected.items())
