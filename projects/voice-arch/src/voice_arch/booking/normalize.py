"""Pure normalisers for spoken / typed booking fields: both sides of a comparison go through the same one.

`normalize_text` and `contains_phrase` are copied from mini-rag `scoring.py:56-69`.
"""

import re
import unicodedata
from typing import Final

_APOSTROPHES: Final = {
    "'",
    "`",
    "\N{RIGHT SINGLE QUOTATION MARK}",
    "\N{LEFT SINGLE QUOTATION MARK}",
    "\N{MODIFIER LETTER APOSTROPHE}",
}
_ARTICLES: Final = {"a", "an", "the"}

_DIGIT_WORDS: Final = {
    "oh": "0",
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
}
_REPEATS: Final = {"double": 2, "triple": 3}

_STREET_WORDS: Final = {
    "street": "st",
    "road": "rd",
    "avenue": "ave",
    "drive": "dr",
    "lane": "ln",
    "boulevard": "blvd",
    "court": "ct",
    "apartment": "unit",
    "apt": "unit",
}
_STATES: Final = {
    "alabama": "al", "alaska": "ak", "arizona": "az", "arkansas": "ar", "california": "ca",
    "colorado": "co", "connecticut": "ct", "delaware": "de", "florida": "fl", "georgia": "ga",
    "hawaii": "hi", "idaho": "id", "illinois": "il", "indiana": "in", "iowa": "ia",
    "kansas": "ks", "kentucky": "ky", "louisiana": "la", "maine": "me", "maryland": "md",
    "massachusetts": "ma", "michigan": "mi", "minnesota": "mn", "mississippi": "ms", "missouri": "mo",
    "montana": "mt", "nebraska": "ne", "nevada": "nv", "new hampshire": "nh", "new jersey": "nj",
    "new mexico": "nm", "new york": "ny", "north carolina": "nc", "north dakota": "nd", "ohio": "oh",
    "oklahoma": "ok", "oregon": "or", "pennsylvania": "pa", "rhode island": "ri", "south carolina": "sc",
    "south dakota": "sd", "tennessee": "tn", "texas": "tx", "utah": "ut", "vermont": "vt",
    "virginia": "va", "washington": "wa", "west virginia": "wv", "wisconsin": "wi", "wyoming": "wy",
}  # fmt: skip
_ZIP: Final = re.compile(r"\d{5}")
# A run of >= 2 single letters separated by "-" or spaces ("s m y t h"); a lone initial is not a run.
_SPELLED: Final = re.compile(r"(?<![^\W\d_])[^\W\d_](?:[-\s][^\W\d_](?![^\W\d_]))+(?![^\W\d_])")


def spoken_digits(text: str) -> str:
    """Digits of a spoken or typed number: "oh"/"zero".."nine", "double X"/"triple X", digit characters."""
    out: list[str] = []
    repeat = 1
    for token in re.findall(r"[a-z0-9]+", text.casefold()):
        if token in _REPEATS:
            repeat = _REPEATS[token]
            continue
        digits = _DIGIT_WORDS.get(token) or "".join(ch for ch in token if ch.isdigit())
        # "double"/"triple" only repeat a single digit; before anything else they are dropped.
        out.append(digits * repeat if len(digits) == 1 else digits)
        repeat = 1
    return "".join(out)


def normalize_phone(text: str) -> str:
    digits = spoken_digits(text)
    return digits[1:] if len(digits) == 11 and digits.startswith("1") else digits


def _punctuation_to_space(text: str) -> str:
    return "".join(" " if unicodedata.category(ch)[0] in {"P", "S"} else ch for ch in text)


def _map_address_tokens(tokens: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(tokens):
        pair = " ".join(tokens[i : i + 2])
        if pair in _STATES:
            out.append(_STATES[pair])
            i += 2
            continue
        word = tokens[i]
        out.append(_STATES.get(word) or _STREET_WORDS.get(word) or word)
        i += 1
    return out


def normalize_address(text: str) -> str:
    tokens = _punctuation_to_space(unicodedata.normalize("NFKC", text).casefold()).split()
    mapped = _map_address_tokens(tokens)
    if len(mapped) > 1 and _ZIP.fullmatch(mapped[-1]):
        mapped.pop()
    return " ".join(mapped)


def normalize_name(text: str) -> str:
    """Dots and apostrophes go first, so "S. M. Y. T. H." and "S-M-Y-T-H" both join to "smyth"."""
    text = unicodedata.normalize("NFKC", text)
    text = "".join(ch for ch in text if ch != "." and ch not in _APOSTROPHES)
    text = _SPELLED.sub(lambda m: re.sub(r"[-\s]", "", m.group()), text)
    return " ".join(text.casefold().split())


def normalize_text(text: str) -> str:
    """Lowercase, NFKC, drop apostrophes, punctuation -> space, drop articles, collapse whitespace."""
    text = unicodedata.normalize("NFKC", text).lower()
    chars: list[str] = []
    for ch in text:
        if ch in _APOSTROPHES:
            continue
        chars.append(" " if unicodedata.category(ch)[0] in {"P", "S"} else ch)
    return " ".join(tok for tok in "".join(chars).split() if tok not in _ARTICLES)


def contains_phrase(hay: str, needle: str) -> bool:
    """Token-boundary containment on normalised text, so `5050` does not match `50505`."""
    return bool(needle) and f" {needle} " in f" {hay} "
