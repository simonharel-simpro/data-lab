"""The fixed appointment calendar (U-7, D-18). Times are naive local ("America/Chicago"); `today` is never read."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Final, Literal

REFERENCE_DATE: Final = date(2026, 11, 9)  # a Monday

Part = Literal["morning", "afternoon"]


class UnknownSlotError(Exception):
    pass


@dataclass(frozen=True)
class Slot:
    id: str
    start: datetime
    booked: bool


def _slot(day: int, hour: int, booked: bool = False) -> Slot:
    return Slot(f"ST_202611{day:02d}_{hour:02d}00", datetime(2026, 11, day, hour), booked)


CALENDAR: Final[tuple[Slot, ...]] = (
    _slot(9, 9, booked=True),
    _slot(9, 14),
    _slot(10, 9),
    _slot(10, 14),
    _slot(10, 16, booked=True),
    _slot(11, 11),
    _slot(11, 16),
    _slot(12, 9, booked=True),
    _slot(12, 14),
    _slot(13, 9),
    _slot(13, 11),
    _slot(13, 16),
)


def available(day: date | None = None, part: Part | None = None, taken: frozenset[str] = frozenset()) -> list[Slot]:
    """Free slots, earliest first; `booked` is the fixture, `taken` the session's own bookings."""
    return [
        slot
        for slot in CALENDAR
        if not slot.booked
        and slot.id not in taken
        and (day is None or slot.start.date() == day)
        and (part is None or (slot.start.hour < 12) == (part == "morning"))
    ]


def describe(slot: Slot) -> str:
    """E.g. "Tuesday November 10 at 2 PM"."""
    start = slot.start
    hour = start.hour % 12 or 12
    suffix = "AM" if start.hour < 12 else "PM"
    minutes = f":{start.minute:02d}" if start.minute else ""
    return f"{start:%A %B} {start.day} at {hour}{minutes} {suffix}"


def slot_by_id(slot_id: str) -> Slot:
    for slot in CALENDAR:
        if slot.id == slot_id:
            return slot
    raise UnknownSlotError(slot_id)
