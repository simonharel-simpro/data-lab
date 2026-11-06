"""The only code that writes the record. Each function returns the reply the LLM sees (pure, no LiveKit)."""

import re
from collections.abc import Collection
from datetime import date
from typing import Final

from voice_arch.booking.calendar import Part, UnknownSlotError, available, describe, slot_by_id
from voice_arch.booking.record import SCORED_FIELDS, BookingRecord, ProblemType, is_scored_field

NOTED: Final = "Noted."
CONFIRMED: Final = "Confirmed."
_ISO_DAY: Final = re.compile(r"\d{4}-\d{2}-\d{2}")
_MAX_OFFERED: Final = 2
_PARTS: Final[dict[str, Part]] = {"morning": "morning", "afternoon": "afternoon"}


def apply_record(record: BookingRecord, field: str, value: str) -> str:
    if not is_scored_field(field):
        return f"Unknown field {field!r}; use one of name, phone, address, problem_type, slot_id."
    try:
        record.set_field(field, value)
    except ValueError:
        types = ", ".join(t.value for t in ProblemType)
        return f"{value!r} is not a problem type; use one of {types}."
    return NOTED


def _parse_day(day: str) -> date | None:
    if not _ISO_DAY.fullmatch(day):
        return None
    try:
        return date.fromisoformat(day)
    except ValueError:
        return None


def apply_check_slots(day: str | None, part: str | None, taken: Collection[str]) -> str:
    """At most two free slots, earliest first, with their ids (the ids go to `choose_slot`)."""
    if part is not None and part not in _PARTS:
        return "Use morning or afternoon."
    parsed = None if day is None else _parse_day(day)
    if day is not None and parsed is None:
        return "Use a date like 2026-11-10."
    slots = available(parsed, None if part is None else _PARTS[part], frozenset(taken))
    if not slots:
        return "No free slot then; offer another day."
    return "Free: " + "; ".join(f"{describe(s)} ({s.id})" for s in slots[:_MAX_OFFERED])


def apply_choose_slot(record: BookingRecord, slot_id: str, taken: set[str]) -> str:
    """Re-choosing releases the previous slot; a failed choice leaves record and `taken` untouched (U-17)."""
    try:
        slot = slot_by_id(slot_id)
    except UnknownSlotError:
        return "That slot doesn't exist. Call check_slots to see the free ones."
    if slot.booked or slot_id in taken - {record.slot_id}:
        return "That slot is taken. Offer another one from check_slots."
    if record.slot_id is not None:
        taken.discard(record.slot_id)
    record.set_field("slot_id", slot_id)
    taken.add(slot_id)
    return f"Chosen: {describe(slot)}."


def apply_confirm(record: BookingRecord) -> str:
    missing = record.missing()
    if missing:
        return f"Still missing: {', '.join(missing)}"
    record.confirm()
    return CONFIRMED


def render_call_record(record: BookingRecord) -> str:
    """The call record arch C injects into each task's instructions."""
    filled = [f"{f}: {getattr(record, f)}" for f in SCORED_FIELDS if getattr(record, f) is not None]
    lines = ["Call record so far:", *filled]
    if record.corrections:
        lines.append(f"Corrected: {', '.join(record.corrections)}")
    lines.append(f"Missing: {', '.join(record.missing())}")
    return "\n".join(lines)
