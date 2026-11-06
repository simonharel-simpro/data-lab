"""The six scripted callers and the expected booking each one should end up with (U-5, U-7, U-17, U-25)."""

import json
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ValidationError

from voice_arch.booking.calendar import UnknownSlotError, slot_by_id
from voice_arch.booking.record import ExpectedRecord, ProblemType


class Behaviour(StrEnum):
    SELF_CORRECTION = "self_correction"
    OUT_OF_ORDER = "out_of_order"
    INTERRUPTER = "interrupter"
    SLOT_CHANGE = "slot_change"
    SPELLER = "speller"
    VAGUE_PROBLEM = "vague_problem"


class PersonaError(ValueError):
    def __init__(self, line: int, reason: str) -> None:
        super().__init__(f"personas line {line}: {reason}")
        self.line = line
        self.reason = reason


class Persona(BaseModel):
    id: str
    behaviour: Behaviour
    instructions: str
    interjections: list[str] = []
    expected_record: ExpectedRecord


def _check_expected(line: int, expected: ExpectedRecord) -> None:
    try:
        ProblemType(expected.problem_type)
    except ValueError as err:
        raise PersonaError(line, f"unknown problem_type {expected.problem_type!r}") from err
    try:
        slot = slot_by_id(expected.slot_id)
    except UnknownSlotError as err:
        raise PersonaError(line, f"slot {expected.slot_id} is not in the calendar") from err
    if slot.booked:
        raise PersonaError(line, f"slot {expected.slot_id} is already booked")


def _parse_line(line: int, text: str) -> Persona:
    try:
        persona = Persona.model_validate_json(text)
    except ValidationError as err:
        # Field paths and messages only: never echo the input values.
        reasons = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in err.errors())
        raise PersonaError(line, reasons) from err
    _check_expected(line, persona.expected_record)
    return persona


def _check_json(line: int, text: str) -> None:
    try:
        json.loads(text)
    except json.JSONDecodeError as err:
        raise PersonaError(line, f"not JSON: {err.msg}") from err


def load_personas(path: Path) -> list[Persona]:
    numbered = [(n, text) for n, text in enumerate(path.read_text(encoding="utf-8").splitlines(), 1) if text.strip()]
    personas: list[Persona] = []
    for line, text in numbered:
        _check_json(line, text)
        personas.append(_parse_line(line, text))
    ids = [p.id for p in personas]
    if len(set(ids)) != len(ids):
        raise PersonaError(0, f"duplicate persona id in {sorted(ids)}")
    if {p.behaviour for p in personas} != set(Behaviour) or len(personas) != len(Behaviour):
        raise PersonaError(0, f"expected exactly one persona per behaviour {[b.value for b in Behaviour]}")
    return personas
