from voice_arch.fields import args_correct, field_errors


def test_field_errors_flags_wrong_phone_only() -> None:
    transcript = "my name is John Miller and my number is 415 555 0018"
    truth = {"phone": "4155550019", "name": "John Miller"}

    assert field_errors(transcript, truth) == {"phone": True, "name": False}


def test_field_errors_accepts_spoken_phone() -> None:
    truth = {"phone": "4155550134"}

    assert field_errors("it is four one five five five five oh one three four", truth) == {"phone": False}


def test_f_10_empty_transcript_counts_as_stt_error_in_bench() -> None:
    truth = {"name": "John Miller", "phone": "4155550134", "address": "12 Oak Road", "slot": "Tuesday afternoon"}

    assert field_errors("", truth) == {"name": True, "phone": True, "address": True, "slot": True}


def test_u_15_llm_arg_accuracy_compares_normalised_values() -> None:
    assert args_correct({"phone": "(415) 555-0134"}, {"phone": "4155550134"}) is True


def test_args_correct_exact_for_enum_and_slot_fields() -> None:
    assert args_correct({"problem_type": "hvac"}, {"problem_type": "hvac"}) is True
    assert args_correct({"problem_type": "HVAC"}, {"problem_type": "hvac"}) is False
    assert args_correct({"slot_id": "ST_20261110_0900"}, {"slot_id": "ST_20261110_1400"}) is False


def test_args_correct_false_on_missing_or_extra_keys() -> None:
    assert args_correct({}, {"name": "x"}) is False
    assert args_correct({"name": "x", "phone": "1"}, {"name": "x"}) is False


def test_args_correct_name_and_address_use_their_normalisers() -> None:
    assert args_correct({"name": "S-M-Y-T-H"}, {"name": "Smyth"}) is True
    assert args_correct({"address": "12 oak road, springfield illinois"}, {"address": "12 Oak Rd Springfield IL"})


def test_field_errors_name_followed_by_punctuation_still_matches() -> None:
    transcript = "Hi, this is Maria Garcia, that's G-A-R-C-I-A."

    assert field_errors(transcript, {"name": "Maria Garcia"}) == {"name": False}
