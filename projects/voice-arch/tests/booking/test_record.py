import pytest
from pydantic import ValidationError

from voice_arch.booking.record import (
    SCORED_FIELDS,
    BookingRecord,
    ExpectedRecord,
    IncompleteRecordError,
    ProblemType,
    is_exact,
)

EXPECTED = ExpectedRecord(
    name="jon oneil",
    phone="4155550134",
    address="27 wattle st austin tx",
    problem_type="plumbing",
    slot_id="ST_20261110_1400",
)


def _full_record(confirmed: bool = False) -> BookingRecord:
    return BookingRecord(
        name="Jon O'Neil",
        phone="+1 (415) 555-0134",
        address="27 Wattle Street, Austin, Texas 73301",
        problem_type=ProblemType.PLUMBING,
        slot_id="ST_20261110_1400",
        confirmed=confirmed,
    )


def test_u_2_record_edit_after_confirm_resets_confirmed() -> None:
    record = _full_record(confirmed=True)

    record.set_field("slot_id", "ST_20261110_0900")

    assert (record.confirmed, record.corrections) == (False, ["slot_id"])


def test_u_2_unconfirmed_correct_record_is_not_exact() -> None:
    exact, per_field = is_exact(_full_record(confirmed=False), EXPECTED)

    assert (exact, per_field) == (False, dict.fromkeys(SCORED_FIELDS, True))


def test_u_13_missing_field_counts_as_incorrect() -> None:
    record = _full_record(confirmed=True)
    record.address = None

    exact, per_field = is_exact(record, EXPECTED)

    assert exact is False
    assert per_field["address"] is False


def test_none_record_is_all_wrong() -> None:
    assert is_exact(None, EXPECTED) == (False, dict.fromkeys(SCORED_FIELDS, False))


def test_confirm_incomplete_raises() -> None:
    record = _full_record()
    record.phone = None

    with pytest.raises(IncompleteRecordError) as excinfo:
        record.confirm()

    assert excinfo.value.missing == ["phone"]
    assert record.confirmed is False


def test_exact_record_after_normalisation() -> None:
    exact, per_field = is_exact(_full_record(confirmed=True), EXPECTED)

    assert (exact, per_field) == (True, dict.fromkeys(SCORED_FIELDS, True))


def test_u_25_expected_record_keys_equal_scored_fields() -> None:
    assert tuple(ExpectedRecord.model_fields) == SCORED_FIELDS
    with pytest.raises(ValidationError):
        ExpectedRecord(**EXPECTED.model_dump(), extra_key="x")  # pyright: ignore[reportCallIssue]  # bad kwarg


def test_invalid_problem_type_rejected() -> None:
    record = BookingRecord()

    with pytest.raises(ValueError, match="roofing"):
        record.set_field("problem_type", "roofing")

    assert record.problem_type is None


def test_missing_lists_unset_fields_in_scored_order() -> None:
    record = BookingRecord(name="A", slot_id="ST_20261110_1400")

    assert record.missing() == ["phone", "address", "problem_type"]


def test_set_field_same_value_is_not_a_correction() -> None:
    record = BookingRecord(name="A")

    record.set_field("name", "A")

    assert record.corrections == []


def test_confirm_complete_record_sets_confirmed() -> None:
    record = _full_record()

    record.confirm()

    assert record.confirmed is True


def test_wrong_slot_is_exact_false_even_when_confirmed() -> None:
    record = _full_record(confirmed=True)
    record.slot_id = "ST_20261110_0900"

    exact, per_field = is_exact(record, EXPECTED)

    assert exact is False
    assert per_field["slot_id"] is False
