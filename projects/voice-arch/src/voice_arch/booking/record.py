"""The booking record the agent fills and the exactness check that scores it (U-2, U-13, U-25)."""

from collections.abc import Callable
from enum import StrEnum
from typing import Final, Literal, TypeGuard

from pydantic import BaseModel, ConfigDict, Field

from voice_arch.booking.normalize import normalize_address, normalize_name, normalize_phone

ScoredField = Literal["name", "phone", "address", "problem_type", "slot_id"]
SCORED_FIELDS: Final[tuple[ScoredField, ...]] = ("name", "phone", "address", "problem_type", "slot_id")


class ProblemType(StrEnum):
    PLUMBING = "plumbing"
    ELECTRICAL = "electrical"
    HVAC = "hvac"
    APPLIANCE = "appliance"
    OTHER = "other"


class IncompleteRecordError(Exception):
    def __init__(self, missing: list[str]) -> None:
        super().__init__(f"record incomplete, missing: {', '.join(missing)}")
        self.missing = missing


def is_scored_field(field: str) -> TypeGuard[ScoredField]:
    return field in SCORED_FIELDS


class BookingRecord(BaseModel):
    name: str | None = None
    phone: str | None = None
    address: str | None = None
    problem_type: ProblemType | None = None
    slot_id: str | None = None
    confirmed: bool = False
    corrections: list[str] = Field(default_factory=list)

    def set_field(self, field: ScoredField, value: str) -> None:
        """Any write un-confirms the record (U-2); overwriting a different value is logged as a correction."""
        if not is_scored_field(field):
            raise ValueError(f"unknown field {field!r}")
        new = ProblemType(value) if field == "problem_type" else value
        old = getattr(self, field)
        if old is not None and old != new:
            self.corrections.append(field)
        setattr(self, field, new)
        self.confirmed = False

    def missing(self) -> list[str]:
        return [field for field in SCORED_FIELDS if getattr(self, field) is None]

    def confirm(self) -> None:
        missing = self.missing()
        if missing:
            raise IncompleteRecordError(missing)
        self.confirmed = True


class ExpectedRecord(BaseModel):
    """The scripted caller's truth: exactly the scored fields, nothing else (U-25)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    phone: str
    address: str
    problem_type: str
    slot_id: str


_NORMALISERS: Final[dict[str, Callable[[str], str]]] = {
    "name": normalize_name,
    "phone": normalize_phone,
    "address": normalize_address,
}


def _field_equal(field: ScoredField, actual: str | None, expected: str) -> bool:
    if actual is None:
        return False
    normalise = _NORMALISERS.get(field)
    if normalise is None:  # problem_type and slot_id compare exactly
        return actual == expected
    return normalise(actual) == normalise(expected)


def _text(record: BookingRecord, field: ScoredField) -> str | None:
    value = getattr(record, field)
    return None if value is None else str(value)


def is_exact(actual: BookingRecord | None, expected: ExpectedRecord) -> tuple[bool, dict[str, bool]]:
    """Per-field normalised equality; exact also needs `confirmed` (U-2). A missing record is all wrong (U-13)."""
    if actual is None:
        return False, dict.fromkeys(SCORED_FIELDS, False)
    per_field = {field: _field_equal(field, _text(actual, field), getattr(expected, field)) for field in SCORED_FIELDS}
    return all(per_field.values()) and actual.confirmed, per_field
