import json
from typing import Any

import pytest

from datalab.ledger import Decision, LedgerError, RunLedger, Status, decide, parse, produce, redo
from datalab.ledger_model import TRANSITIONS, Kind, contract
from tests.conftest import REPO_ROOT
from tests.ledger_support import vector

_LAST = contract().sequences[Kind.COMPARISON][-1]


def _at(status: Status) -> RunLedger:
    """comparison-complete rewound so its last milestone (current) has `status`."""
    run: dict[str, Any] = vector("comparison-complete")
    if status is not Status.VALIDATED:
        run["decisions_log"] = [e for e in run["decisions_log"] if e["milestone"] != _LAST]
        artifacts = ["report.html"] if status is Status.PRODUCED else []
        run["milestones"][_LAST] = {"status": status.value, "artifacts": artifacts, "decision": None}
    return parse(json.dumps(run))


def _apply(lg: RunLedger, decision: Decision | None) -> RunLedger:
    if decision is None:
        return produce(lg, _LAST, ["report.html"])
    return decide(lg, _LAST, decision, "because")


_PAIRS = [(s, d) for s in Status for d in (None, *Decision)]


@pytest.mark.parametrize(("status", "decision"), _PAIRS, ids=[f"{s}-{d}" for s, d in _PAIRS])
def test_transitions_table_matches_ops(status: Status, decision: Decision | None) -> None:
    lg = _at(status)

    if (status, decision) not in TRANSITIONS:
        with pytest.raises(LedgerError):
            _apply(lg, decision)
        return
    assert _apply(lg, decision).milestones[_LAST].status is TRANSITIONS[(status, decision)]


@pytest.mark.parametrize("status", list(Status))
def test_redo_resets_a_started_milestone_from_any_status(status: Status) -> None:
    result = redo(_at(status), _LAST)

    assert result.milestones[_LAST].status is Status.TODO
    assert result.current_milestone == _LAST


def _rendered(status: Status, decision: Decision | None, after: Status) -> str:
    return f"{status} + {decision or 'produce'} → {after}"


def test_transitions_table_matches_architecture_md() -> None:
    doc = (REPO_ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    lines = {line.strip() for line in doc.splitlines()}

    missing = [_rendered(s, d, a) for (s, d), a in TRANSITIONS.items() if _rendered(s, d, a) not in lines]

    assert missing == []
    assert len(TRANSITIONS) == 5
