import pytest

from voice_arch.booking.normalize import (
    contains_phrase,
    normalize_address,
    normalize_name,
    normalize_phone,
    normalize_text,
    spoken_digits,
)


def test_spoken_digits_maps_oh_double_triple() -> None:
    assert spoken_digits("oh four one two double five triple nine") == "041255999"


def test_u_4_phone_spoken_double_and_oh_normalise_to_digits() -> None:
    assert normalize_phone("four one five, five double five, oh one three four") == "4155550134"


def test_phone_drops_leading_country_code() -> None:
    assert normalize_phone("1 415 555 0134") == "4155550134"


def test_spoken_digits_keeps_digit_characters_and_drops_other_words() -> None:
    assert spoken_digits("call (415) 555-0134 please") == "4155550134"


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("12 Oak Road, Springfield, IL", "12 oak rd springfield illinois 62704"),
        ("5 Elm St, New York, NY", "5 elm street new york new york"),
    ],
)
def test_address_variants_are_equal(left: str, right: str) -> None:
    assert normalize_address(left) == normalize_address(right)


def test_address_maps_unit_words_and_keeps_distinct_streets_distinct() -> None:
    assert normalize_address("Apartment 4B, 221 Baker Avenue") == "unit 4b 221 baker ave"
    assert normalize_address("12 Oak Road") != normalize_address("12 Oak Lane")


def test_u_8_smyth_does_not_match_smith() -> None:
    assert normalize_name("Smyth") != normalize_name("Smith")


def test_u_24_spelled_letters_normalise_to_joined_name() -> None:
    assert normalize_name("S-M-Y-T-H") == "smyth"
    assert normalize_name("s m y t h") == "smyth"


def test_name_drops_apostrophe_and_dots_and_keeps_initial_apart() -> None:
    assert normalize_name("Ryan O'Neil") == "ryan oneil"
    assert normalize_name("John A Smith") == "john a smith"


def test_contains_phrase_respects_token_boundaries() -> None:
    assert contains_phrase(normalize_text("My name is John Miller."), normalize_text("john miller"))
    assert not contains_phrase(normalize_text("room 50505"), "5050")
