"""Invariants I-1..I-15 of a `RunLedger`, checked in number order; the first failure wins. Pure."""

import re
from collections.abc import Callable
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Final

from datalab.ledger_model import DATASET, MODELING, Decision, Kind, Status, contract

if TYPE_CHECKING:
    from datalab.ledger_model import RunLedger

_DRIVE: Final = re.compile(r"^[A-Za-z]:")


def _i1(lg: "RunLedger") -> str | None:
    seq = lg.sequence()
    if set(lg.milestones) != set(seq):
        return f"I-1: milestones must be exactly {list(seq)} for a {lg.kind} ledger, got {sorted(lg.milestones)}"
    return None


def _i2(lg: "RunLedger") -> str | None:
    for m, e in lg.milestones.items():
        if e.status is Status.TODO and (e.decision is not None or e.artifacts):
            return f"I-2: {m} is todo, so it has no decision and no artifacts"
    return None


def _i3(lg: "RunLedger") -> str | None:
    for m, e in lg.milestones.items():
        if e.status is Status.VALIDATED and e.decision is not Decision.VALIDATE:
            return f"I-3: {m} is validated, so its decision must be validate"
        if e.status is Status.PRODUCED and e.decision not in (None, Decision.CORRECT):
            return f"I-3: {m} is produced, so its decision must be null or correct"
    return None


def _i4(lg: "RunLedger") -> str | None:
    for m, e in lg.milestones.items():
        if e.status is not Status.TODO and not e.artifacts:
            return f"I-4: {m} is {e.status} but lists no artifact"
    return None


def _i5(lg: "RunLedger") -> str | None:
    unvalidated: str | None = None
    for m in lg.sequence():
        status = lg.milestones[m].status
        if status is not Status.TODO and unvalidated is not None:
            return f"I-5: {m} is {status} but {unvalidated} is not validated"
        if status is not Status.VALIDATED and unvalidated is None:
            unvalidated = m
    return None


def _i6(lg: "RunLedger") -> str | None:
    seq = lg.sequence()
    pending = [m for m in seq if lg.milestones[m].status is not Status.VALIDATED]
    expected = pending[0] if pending else seq[-1]
    if lg.current_milestone != expected:
        return f"I-6: current_milestone must be {expected}, got {lg.current_milestone}"
    return None


def _i7(lg: "RunLedger") -> str | None:
    if lg.kind is Kind.COMPARISON and lg.features is not None:
        return "I-7: a comparison ledger has no features"
    return None


def _i8(lg: "RunLedger") -> str | None:
    for m, e in lg.milestones.items():
        if e.decision is None:
            continue
        logged = [entry.decision for entry in lg.decisions_log if entry.milestone == m]
        if not logged or logged[-1] is not e.decision:
            return f"I-8: {m} has decision {e.decision} but its last log entry is {logged[-1] if logged else None}"
    return None


def _i9(lg: "RunLedger") -> str | None:
    for entry in lg.decisions_log:
        if entry.milestone not in lg.sequence():
            return f"I-9: decisions_log names {entry.milestone!r}, which is not in the sequence"
    return None


def _i10(lg: "RunLedger") -> str | None:
    seq = lg.sequence()
    for m in seq[seq.index(contract().freeze_after) + 1 :]:
        if lg.milestones[m].status is not Status.TODO and lg.split_sha256 is None:
            return f"I-10: {m} started but the split is not frozen (split_sha256 is null)"
    return None


def _i11(lg: "RunLedger") -> str | None:
    if lg.milestones[DATASET].status is Status.VALIDATED and lg.dataset is None:
        return "I-11: dataset is validated but dataset is null"
    return None


def _bad_artifact(path: str) -> bool:
    if path.startswith("/") or "\\" in path or _DRIVE.match(path) or ".." in path.split("/"):
        return True
    return PurePosixPath(path).as_posix() == "."


def _i12(lg: "RunLedger") -> str | None:
    for m, e in lg.milestones.items():
        for path in e.artifacts:
            if _bad_artifact(path):
                return f"I-12: {m} artifact {path!r} must be a relative POSIX path inside the project"
    return None


def _i13(lg: "RunLedger") -> str | None:
    validated = lg.milestones[MODELING].status is Status.VALIDATED
    if (lg.winner is not None) != validated:
        return "I-13: winner must be set exactly when modeling is validated"
    return None


def _i14(lg: "RunLedger") -> str | None:
    seen: set[str] = set()
    for look in lg.test_looks:
        if look.split_sha256 in seen and not look.note.strip():
            return f"I-14: a repeated test look on split {look.split_sha256[:8]} needs a note"
        seen.add(look.split_sha256)
    return None


def _i15(lg: "RunLedger") -> str | None:
    if lg.milestones[MODELING].status is not Status.TODO and lg.data_sha256 is None:
        return "I-15: modeling started but data_sha256 is null"
    return None


_RULES: Final[tuple[Callable[["RunLedger"], str | None], ...]] = (
    _i1, _i2, _i3, _i4, _i5, _i6, _i7, _i8, _i9, _i10, _i11, _i12, _i13, _i14, _i15,
)  # fmt: skip


def first_violation(lg: "RunLedger") -> str | None:
    for rule in _RULES:
        message = rule(lg)
        if message is not None:
            return message
    return None
