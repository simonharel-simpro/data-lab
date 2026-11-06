from voice_arch.booking.actions import (
    WAIT_FOR_CALLER,
    apply_check_slots,
    apply_choose_slot,
    apply_confirm,
    apply_record,
    render_call_record,
)
from voice_arch.booking.record import BookingRecord, ProblemType


def test_u_17_choose_booked_slot_returns_error_and_keeps_record() -> None:
    record, taken = BookingRecord(), set[str]()

    reply = apply_choose_slot(record, "ST_20261109_0900", taken)

    assert "taken" in reply
    assert record.slot_id is None
    assert taken == set()


def test_choose_unknown_slot_returns_error() -> None:
    record, taken = BookingRecord(slot_id="ST_20261110_1400"), {"ST_20261110_1400"}

    reply = apply_choose_slot(record, "ST_x", taken)

    assert "doesn't exist" in reply
    assert (record.slot_id, taken) == ("ST_20261110_1400", {"ST_20261110_1400"})


def test_choose_free_slot_records_it_and_marks_it_taken() -> None:
    record, taken = BookingRecord(), set[str]()

    reply = apply_choose_slot(record, "ST_20261110_1400", taken)

    assert "Tuesday November 10 at 2 PM" in reply
    assert (record.slot_id, taken) == ("ST_20261110_1400", {"ST_20261110_1400"})


def test_rechoosing_a_slot_releases_the_previous() -> None:
    record, taken = BookingRecord(), set[str]()
    first, second = "ST_20261110_1400", "ST_20261110_0900"

    apply_choose_slot(record, first, taken)
    apply_choose_slot(record, second, taken)

    assert taken == {second}
    assert record.slot_id == second


def test_rechoosing_the_same_slot_keeps_it() -> None:
    record, taken = BookingRecord(), set[str]()
    apply_choose_slot(record, "ST_20261110_1400", taken)

    reply = apply_choose_slot(record, "ST_20261110_1400", taken)

    assert "taken" not in reply
    assert taken == {"ST_20261110_1400"}


def test_choose_slot_taken_by_another_session_state_is_refused() -> None:
    record, taken = BookingRecord(), {"ST_20261110_0900"}

    reply = apply_choose_slot(record, "ST_20261110_0900", taken)

    assert "taken" in reply
    assert record.slot_id is None


def test_confirm_incomplete_lists_missing_fields() -> None:
    record = BookingRecord(name="Jon")

    reply = apply_confirm(record, caller_replied=True)

    assert reply == "Still missing: phone, address, problem_type, slot_id"
    assert record.confirmed is False


def test_confirm_complete_record_confirms() -> None:
    record = BookingRecord(
        name="Jon", phone="1", address="2", problem_type=ProblemType.HVAC, slot_id="ST_20261110_1400"
    )

    assert apply_confirm(record, caller_replied=True) == "Confirmed."
    assert record.confirmed is True


def test_confirm_complete_record_waits_when_the_caller_has_not_replied() -> None:
    record = BookingRecord(
        name="Jon", phone="1", address="2", problem_type=ProblemType.HVAC, slot_id="ST_20261110_1400"
    )

    assert apply_confirm(record, caller_replied=False) == WAIT_FOR_CALLER
    assert record.confirmed is False


def test_render_call_record_lists_missing_and_corrections() -> None:
    record = BookingRecord()
    apply_record(record, "name", "Jon")
    apply_record(record, "phone", "415 555 0100")
    apply_record(record, "phone", "415 555 0134")

    text = render_call_record(record)

    assert "name: Jon" in text
    assert "phone: 415 555 0134" in text
    assert "Corrected: phone" in text
    assert "Missing: address, problem_type, slot_id" in text


def test_check_slots_rejects_non_iso_day() -> None:
    assert apply_check_slots("next tuesday", None, frozenset()) == "Use a date like 2026-11-10."


def test_check_slots_lists_at_most_two_earliest_free_slots_with_ids() -> None:
    reply = apply_check_slots("2026-11-11", None, frozenset())

    assert reply == (
        "Free: Wednesday November 11 at 11 AM (ST_20261111_1100); Wednesday November 11 at 4 PM (ST_20261111_1600)"
    )


def test_check_slots_without_day_returns_earliest_free_overall() -> None:
    reply = apply_check_slots(None, None, frozenset())

    assert reply.startswith("Free: Monday November 9 at 2 PM (ST_20261109_1400); Tuesday November 10 at 9 AM")
    assert reply.count("ST_") == 2


def test_check_slots_with_nothing_free_says_so() -> None:
    reply = apply_check_slots("2026-11-10", "afternoon", frozenset({"ST_20261110_1400"}))

    assert reply == "No free slot then; offer another day."


def test_check_slots_rejects_unknown_part() -> None:
    assert apply_check_slots(None, "evening", frozenset()) == "Use morning or afternoon."


def test_record_invalid_problem_type_returns_error_text_and_keeps_record() -> None:
    record = BookingRecord()

    reply = apply_record(record, "problem_type", "roofing")

    assert "plumbing" in reply
    assert record.problem_type is None


def test_record_unknown_field_returns_error_text() -> None:
    record = BookingRecord()

    reply = apply_record(record, "confirmed", "yes")

    assert "Unknown field" in reply
    assert record.confirmed is False


def test_record_valid_value_replies_noted() -> None:
    record = BookingRecord()

    assert apply_record(record, "name", "Jon") == "Noted."
    assert record.name == "Jon"
