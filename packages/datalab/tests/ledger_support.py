"""Shared helpers of the ledger tests: the JSON vectors, a project folder on disk, and ledgers built from them."""

import copy
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from datalab.ledger import RunLedger, parse
from tests.conftest import REPO_ROOT

VECTORS = json.loads((REPO_ROOT / "contracts" / "run_ledger_vectors.json").read_text(encoding="utf-8"))
CARD = "---\nname: demo\nmetric:\n  key: score\n  goal: max\n---\n"


def h(char: str) -> str:
    return char * 64


def vector(name: str) -> dict[str, Any]:
    for entry in (*VECTORS["valid"], *VECTORS["invalid"]):
        if entry["name"] == name:
            return copy.deepcopy(entry["run"])
    raise KeyError(name)


def ledger(name: str) -> RunLedger:
    return parse(json.dumps(vector(name)))


def at_modeling(status: str) -> dict[str, Any]:
    """The audit-first-look ledger rewound to modeling: `todo` (data recorded, no winner) or `produced`."""
    run = vector("audit-first-look")
    run["current_milestone"] = "modeling"
    run["milestones"]["audit"] = {"status": "todo", "artifacts": [], "decision": None}
    run["test_looks"], run["winner"] = [], None
    run["decisions_log"] = run["decisions_log"][:3]
    if status == "todo":
        run["milestones"]["modeling"] = {"status": "todo", "artifacts": [], "decision": None}
        run["data_sha256"] = None
    else:
        run["milestones"]["modeling"] = {"status": "produced", "artifacts": ["modeling.md"], "decision": None}
    return run


def after_dataset() -> dict[str, Any]:
    """Comparison with scoping and dataset validated and the split not yet frozen."""
    run = vector("audit-first-look")
    run["current_milestone"], run["split_summary"], run["split_sha256"], run["data_sha256"] = "eda", None, None, None
    for m in ("eda", "modeling"):
        run["milestones"][m] = {"status": "todo", "artifacts": [], "decision": None}
    run["milestones"]["audit"] = {"status": "todo", "artifacts": [], "decision": None}
    run["winner"], run["test_looks"] = None, []
    run["decisions_log"] = run["decisions_log"][:2]
    return run


def artifacts_of(run: dict[str, Any]) -> list[str]:
    return [a for entry in run["milestones"].values() if entry["status"] != "todo" for a in entry["artifacts"]]


def project(tmp_path: Path, run: dict[str, Any] | None = None, files: Iterable[str] | None = None) -> Path:
    folder = tmp_path / "proj"
    folder.mkdir(exist_ok=True)
    (folder / "PROJECT.md").write_text(CARD, encoding="utf-8")
    if run is not None:
        (folder / "run.json").write_text(json.dumps(run), encoding="utf-8")
    for name in artifacts_of(run) if files is None and run is not None else (files or ()):
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text("x", encoding="utf-8")
    return folder
