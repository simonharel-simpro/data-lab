from datetime import date, datetime

import pytest

from voice_arch.booking import calendar
from voice_arch.booking.calendar import CALENDAR, UnknownSlotError, available, describe, slot_by_id

# The 12 ids and the 3 booked ones, from the plan's table (D-18).
PLAN_IDS = (
    "ST_20261109_0900",
    "ST_20261109_1400",
    "ST_20261110_0900",
    "ST_20261110_1400",
    "ST_20261110_1600",
    "ST_20261111_1100",
    "ST_20261111_1600",
    "ST_20261112_0900",
    "ST_20261112_1400",
    "ST_20261113_0900",
    "ST_20261113_1100",
    "ST_20261113_1600",
)
PLAN_BOOKED = {"ST_20261109_0900", "ST_20261110_1600", "ST_20261112_0900"}


def test_calendar_has_the_twelve_planned_slots() -> None:
    assert tuple(slot.id for slot in CALENDAR) == PLAN_IDS
    assert {slot.id for slot in CALENDAR if slot.booked} == PLAN_BOOKED


def test_u_7_calendar_is_independent_of_today(monkeypatch: pytest.MonkeyPatch) -> None:
    class FarFuture(date):
        @classmethod
        def today(cls) -> "FarFuture":
            return cls(2030, 1, 1)

    monkeypatch.setattr(calendar, "date", FarFuture)

    assert tuple(slot.id for slot in available()) == tuple(i for i in PLAN_IDS if i not in PLAN_BOOKED)


def test_available_filters_day_and_part() -> None:
    slots = available(date(2026, 11, 10), "afternoon")

    assert [slot.id for slot in slots] == ["ST_20261110_1400"]


def test_available_excludes_taken() -> None:
    slots = available(date(2026, 11, 13), "morning", frozenset({"ST_20261113_0900"}))

    assert [slot.id for slot in slots] == ["ST_20261113_1100"]


def test_unknown_slot_raises() -> None:
    with pytest.raises(UnknownSlotError):
        slot_by_id("ST_20990101_0900")


def test_slot_by_id_returns_the_slot() -> None:
    assert slot_by_id("ST_20261110_1400").start == datetime(2026, 11, 10, 14, 0)


def test_describe_spells_weekday_date_and_hour() -> None:
    assert describe(slot_by_id("ST_20261110_1400")) == "Tuesday November 10 at 2 PM"
    assert describe(slot_by_id("ST_20261113_1100")) == "Friday November 13 at 11 AM"
