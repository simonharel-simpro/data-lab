"""The experiment ledger (`run.json`): enums, contract loader and strict models. Pure: no mlflow/weaviate."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from typing import Annotated, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from pydantic_core import PydanticCustomError

from datalab.project import ProjectError, repo_root

SHA256 = r"^[0-9a-f]{64}$"
Sha = Annotated[str, Field(pattern=SHA256)]
NonEmpty = Annotated[str, Field(min_length=1)]

# Milestone ids the code names; any other id is data from contracts/milestones.json (decisions.md, ADR 2026-11-08).
DATASET: Final = "dataset"
FEATURES: Final = "features"
MODELING: Final = "modeling"
AUDIT: Final = "audit"


class Status(StrEnum):
    TODO = "todo"
    PRODUCED = "produced"
    VALIDATED = "validated"


class Decision(StrEnum):
    VALIDATE = "validate"
    CORRECT = "correct"
    REDO = "redo"


class Kind(StrEnum):
    TRAINING = "training"
    COMPARISON = "comparison"


# (status before, decision) -> status after; `None` = produce. The ops consult it; ARCHITECTURE.md draws it.
# `redo(m)` is not a row: it resets m and every later milestone from any started status.
TRANSITIONS: Final[Mapping[tuple[Status, Decision | None], Status]] = {
    (Status.TODO, None): Status.PRODUCED,
    (Status.PRODUCED, None): Status.PRODUCED,
    (Status.PRODUCED, Decision.CORRECT): Status.PRODUCED,
    (Status.PRODUCED, Decision.VALIDATE): Status.VALIDATED,
    (Status.PRODUCED, Decision.REDO): Status.TODO,
}


class LedgerError(ValueError):
    """A ledger that breaks the contract or an operation the ledger forbids; the message says which rule."""


@dataclass(frozen=True)
class Contract:
    agents: Mapping[str, str]
    sequences: Mapping[Kind, tuple[str, ...]]
    freeze_after: str


@cache
def contract() -> Contract:
    try:
        path = repo_root() / "contracts" / "milestones.json"
    except ProjectError as err:
        raise LedgerError(str(err)) from err
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        agents = {m["id"]: m["agent"] for m in raw["milestones"]}
        sequences = {Kind(k): tuple(v) for k, v in raw["sequences"].items()}
        freeze_after = raw["freeze_after"]
    except (OSError, ValueError, KeyError, TypeError) as err:
        raise LedgerError(f"{path}: unreadable milestone contract: {err!r}") from err
    if set(sequences) != set(Kind):
        raise LedgerError(f"{path}: sequences must be exactly {sorted(Kind)}, got {sorted(sequences)}")
    return Contract(agents=agents, sequences=sequences, freeze_after=freeze_after)


class _Frozen(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class MilestoneEntry(_Frozen):
    status: Status
    artifacts: tuple[str, ...]
    decision: Decision | None


class Dataset(_Frozen):
    id: NonEmpty
    hash: NonEmpty


class LogEntry(_Frozen):
    milestone: str
    decision: Decision
    note: NonEmpty


class Winner(_Frozen):
    candidate: NonEmpty
    run_id: NonEmpty


class TestLook(_Frozen):
    __test__ = False  # not a pytest class, despite the name

    split_sha256: Sha
    run_id: NonEmpty
    note: str


class RunLedger(_Frozen):
    schema_version: Literal[1]
    kind: Kind
    current_milestone: str
    milestones: dict[str, MilestoneEntry]
    dataset: Dataset | None
    metric: NonEmpty
    split_summary: str | None
    split_sha256: Sha | None
    data_sha256: Sha | None
    features: Annotated[tuple[str, ...], Field(min_length=1)] | None
    winner: Winner | None
    test_looks: tuple[TestLook, ...]
    decisions_log: tuple[LogEntry, ...]

    @field_validator("schema_version", mode="before")
    @classmethod
    def _not_a_bool(cls, value: object) -> object:
        # Literal[1] matches `true` (True == 1); a boolean version is a different document.
        if isinstance(value, bool):
            raise ValueError("schema_version must be the integer 1, not a boolean")
        return value

    def sequence(self) -> tuple[str, ...]:
        return contract().sequences[self.kind]

    @model_validator(mode="after")
    def _invariants(self) -> Self:
        # Imported here: ledger_rules type-checks against RunLedger, so a top-level import would be circular.
        from datalab.ledger_rules import first_violation

        violation = first_violation(self)
        if violation is not None:
            raise PydanticCustomError("ledger_invariant", "{msg}", {"msg": violation})
        return self


def describe(err: ValidationError) -> str:
    """Steps (3)-(4) of the check order: a bare `I-n: ...` invariant message, else `schema: <loc>: <msg>`."""
    first = err.errors()[0]
    if first["type"] == "ledger_invariant":
        return first["msg"]
    loc = ".".join(str(part) for part in first["loc"])
    return f"schema: {loc}: {first['msg']}"
