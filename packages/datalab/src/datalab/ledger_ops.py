"""Pure transitions on a `RunLedger`; each rebuilds via `_revalidate`, never `model_copy` (strict needs JSON mode)."""

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from datalab.ledger_model import (
    Decision,
    Kind,
    LedgerError,
    RunLedger,
    Status,
    TestLook,
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
    return {"status": "todo", "artifacts": [], "decision": None}


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


def produce(lg: RunLedger, milestone: str, artifacts: Sequence[str]) -> RunLedger:
    if _require_current(lg, milestone) is Status.VALIDATED:
        raise LedgerError(f"{milestone} is validated: redo it before producing it again")
    data = _dump(lg)
    data["milestones"][milestone] = {"status": "produced", "artifacts": list(artifacts), "decision": None}
    return _revalidate(data)


def _check_decide_options(
    lg: RunLedger, milestone: str, decision: Decision, redo_from: str | None, winner: Winner | None
) -> None:
    seq = lg.sequence()
    if redo_from is not None and decision is not Decision.REDO:
        raise LedgerError("redo_from only applies to a redo decision")
    if redo_from is not None and (redo_from not in seq or seq.index(redo_from) > seq.index(milestone)):
        raise LedgerError(f"redo_from {redo_from!r} must be {milestone} or an earlier milestone")
    needs_winner = milestone == "modeling" and decision is Decision.VALIDATE
    if needs_winner != (winner is not None):
        raise LedgerError("a winner is required to validate modeling, and only then")


def decide(
    lg: RunLedger,
    milestone: str,
    decision: Decision,
    note: str,
    *,
    redo_from: str | None = None,
    winner: Winner | None = None,
) -> RunLedger:
    if _require_current(lg, milestone) is not Status.PRODUCED:
        raise LedgerError(f"{milestone} is {lg.milestones[milestone].status}: produce it before deciding")
    _check_decide_options(lg, milestone, decision, redo_from, winner)
    data = _dump(lg)
    data["decisions_log"].append({"milestone": milestone, "decision": decision.value, "note": note})
    if decision is Decision.CORRECT:
        data["milestones"][milestone]["decision"] = "correct"
    if decision is Decision.VALIDATE:
        seq = lg.sequence()
        data["milestones"][milestone].update(status="validated", decision="validate")
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
        ("dataset", ("dataset",)),
        ("features", ("features",)),
        ("modeling", ("winner", "data_sha256")),
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
    if lg.milestones["modeling"].status is not Status.TODO:
        raise LedgerError("data_sha256 is recorded before modeling starts")
    try:
        with data_path.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
    except OSError as err:
        raise LedgerError(f"{data_path}: cannot read: {err}") from err
    return _revalidate(_dump(lg) | {"data_sha256": digest})


def look_number(lg: RunLedger, split_sha: str) -> int:
    return 1 + sum(1 for look in lg.test_looks if look.split_sha256 == split_sha)


def test_access_problem(lg: RunLedger, split_sha: str, note: str | None) -> str | None:
    if lg.current_milestone != "audit":
        return f"the test partition is read at the audit; the current milestone is {lg.current_milestone}"
    if lg.milestones["audit"].status is Status.VALIDATED:
        return "the audit is already validated: the test partition is closed"
    if split_sha != lg.split_sha256:
        return "split.json changed since the freeze: its hash differs from run.json split_sha256"
    if look_number(lg, split_sha) > 1 and not (note or "").strip():
        return "a repeated test look on this split needs an expert note"
    return None


def test_access_allowed(lg: RunLedger, split_sha: str, note: str | None = None) -> bool:
    return test_access_problem(lg, split_sha, note) is None


def record_test_look(lg: RunLedger, split_sha: str, run_id: str, note: str | None) -> RunLedger:
    problem = test_access_problem(lg, split_sha, note)
    if problem is not None:
        raise LedgerError(problem)
    look = TestLook(split_sha256=split_sha, run_id=run_id, note=note or "").model_dump(mode="json")
    data = _dump(lg)
    data["test_looks"].append(look)
    return _revalidate(data)


# The names start with "test_" (the contract's wording): keep pytest from collecting them out of test modules.
test_access_problem.__test__ = False  # pyright: ignore[reportFunctionMemberAccess]
test_access_allowed.__test__ = False  # pyright: ignore[reportFunctionMemberAccess]
