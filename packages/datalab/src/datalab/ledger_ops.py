"""Pure transitions on a `RunLedger`; each rebuilds via `_revalidate`, never `model_copy` (strict needs JSON mode)."""

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from datalab.ledger_model import (
    DATASET,
    FEATURES,
    MODELING,
    TRANSITIONS,
    Decision,
    Kind,
    LedgerError,
    RunLedger,
    Status,
    Winner,
    contract,
    describe,
)
from datalab.split import SplitError, read_split, split_sha256

# A ledger as a JSON document: its shape is exactly what RunLedger validates, so a static type adds nothing here.
Doc = dict[str, Any]


def _revalidate(data: Doc) -> RunLedger:
    try:
        return RunLedger.model_validate_json(json.dumps(data))
    except ValidationError as err:
        raise LedgerError(describe(err)) from err


def _dump(lg: RunLedger) -> Doc:
    return lg.model_dump(mode="json")


def _todo() -> Doc:
    return {"status": Status.TODO.value, "artifacts": [], "decision": None}


def new_ledger(kind: Kind, metric: str) -> RunLedger:
    seq = contract().sequences[kind]
    return _revalidate(
        {
            "schema_version": 1,
            "kind": kind.value,
            "current_milestone": seq[0],
            "milestones": {m: _todo() for m in seq},
            "dataset": None,
            "metric": metric,
            "split_summary": None,
            "split_sha256": None,
            "data_sha256": None,
            "features": None,
            "winner": None,
            "test_looks": [],
            "decisions_log": [],
        }
    )


def _require_current(lg: RunLedger, milestone: str) -> Status:
    if milestone not in lg.milestones:
        raise LedgerError(f"unknown milestone {milestone!r}")
    if milestone != lg.current_milestone:
        raise LedgerError(f"{milestone} is not the current milestone ({lg.current_milestone})")
    return lg.milestones[milestone].status


def _next(status: Status, decision: Decision | None, milestone: str) -> Status:
    after = TRANSITIONS.get((status, decision))
    if after is None:
        hint = "produce it before deciding" if decision is not None else "redo it before producing it again"
        raise LedgerError(f"{milestone} is {status}: {hint}")
    return after


def produce(lg: RunLedger, milestone: str, artifacts: Sequence[str]) -> RunLedger:
    _next(_require_current(lg, milestone), None, milestone)
    data = _dump(lg)
    data["milestones"][milestone] = {"status": Status.PRODUCED.value, "artifacts": list(artifacts), "decision": None}
    return _revalidate(data)


def _check_decide_options(
    lg: RunLedger, milestone: str, decision: Decision, redo_from: str | None, winner: Winner | None
) -> None:
    seq = lg.sequence()
    if redo_from is not None and decision is not Decision.REDO:
        raise LedgerError("redo_from only applies to a redo decision")
    if redo_from is not None and (redo_from not in seq or seq.index(redo_from) > seq.index(milestone)):
        raise LedgerError(f"redo_from {redo_from!r} must be {milestone} or an earlier milestone")
    needs_winner = milestone == MODELING and decision is Decision.VALIDATE
    if needs_winner != (winner is not None):
        raise LedgerError("a winner is required to validate modeling, and only then")


def decide(  # noqa: PLR0913  # redo_from / winner: optional kw-only, passed by name by /experiment (#39)
    lg: RunLedger,
    milestone: str,
    decision: Decision,
    note: str,
    *,
    redo_from: str | None = None,
    winner: Winner | None = None,
) -> RunLedger:
    _next(_require_current(lg, milestone), decision, milestone)
    _check_decide_options(lg, milestone, decision, redo_from, winner)
    data = _dump(lg)
    data["decisions_log"].append({"milestone": milestone, "decision": decision.value, "note": note})
    if decision is not Decision.VALIDATE:  # a redo clears a prior `correct` so I-8 sees the log's redo entry
        data["milestones"][milestone]["decision"] = Decision.CORRECT.value if decision is Decision.CORRECT else None
    if decision is Decision.VALIDATE:
        seq = lg.sequence()
        data["milestones"][milestone].update(status=Status.VALIDATED.value, decision=Decision.VALIDATE.value)
        data["current_milestone"] = seq[min(seq.index(milestone) + 1, len(seq) - 1)]
        data["winner"] = winner.model_dump(mode="json") if winner is not None else data["winner"]
    updated = _revalidate(data)
    return redo(updated, redo_from or milestone) if decision is Decision.REDO else updated


def redo(lg: RunLedger, milestone: str) -> RunLedger:
    seq = lg.sequence()
    if milestone not in seq:
        raise LedgerError(f"unknown milestone {milestone!r}")
    index = seq.index(milestone)
    if index > seq.index(lg.current_milestone):
        raise LedgerError(f"cannot redo {milestone}: it has not started (current is {lg.current_milestone})")
    data = _dump(lg)
    for later in seq[index:]:
        data["milestones"][later] = _todo()
    data["current_milestone"] = milestone
    resets = (
        (contract().freeze_after, ("split_sha256", "split_summary")),
        (DATASET, ("dataset",)),
        (FEATURES, ("features",)),
        (MODELING, ("winner", "data_sha256")),
    )
    for anchor, fields in resets:
        if anchor in seq and index <= seq.index(anchor):
            data.update({field: None for field in fields})
    return _revalidate(data)


def freeze_split(lg: RunLedger, split_path: Path, summary: str) -> RunLedger:
    if lg.milestones[contract().freeze_after].status is not Status.VALIDATED:
        raise LedgerError(f"{contract().freeze_after} must be validated before the split is frozen")
    if lg.split_sha256 is not None:
        raise LedgerError("the split is already frozen")
    try:
        read_split(split_path)
        digest = split_sha256(split_path)
    except (SplitError, OSError) as err:
        raise LedgerError(str(err)) from err
    return _revalidate(_dump(lg) | {"split_sha256": digest, "split_summary": summary})


def record_data(lg: RunLedger, data_path: Path) -> RunLedger:
    if lg.split_sha256 is None:
        raise LedgerError("the split must be frozen before the data is recorded")
    if lg.milestones[MODELING].status is not Status.TODO:
        raise LedgerError("data_sha256 is recorded before modeling starts")
    try:
        with data_path.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
    except OSError as err:
        raise LedgerError(f"{data_path}: cannot read: {err}") from err
    return _revalidate(_dump(lg) | {"data_sha256": digest})
