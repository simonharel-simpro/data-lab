"""Filesystem cross-checks V-1..V-3 between run.json, split.json and the project card. Pure: no mlflow/weaviate."""

from pathlib import Path
from typing import Final

from datalab.ledger_model import LedgerError, RunLedger, Status
from datalab.project import ProjectError, card_metric
from datalab.split import split_sha256

SPLIT_JSON: Final = "split.json"


def check_artifacts(project_dir: Path, ledger: RunLedger) -> None:
    root = project_dir.resolve()
    for milestone in ledger.sequence():
        entry = ledger.milestones[milestone]
        for artifact in () if entry.status is Status.TODO else entry.artifacts:
            target = (root / artifact).resolve()
            if not target.is_relative_to(root) or not target.exists():
                raise LedgerError(f"V-1: {milestone} artifact {artifact} is missing or outside {root.name}/")


def check_split_hash(project_dir: Path, ledger: RunLedger) -> None:
    if ledger.split_sha256 is None:
        return
    path = project_dir / SPLIT_JSON
    if not path.is_file():
        raise LedgerError("V-2: run.json freezes a split but split.json is missing")
    if split_sha256(path) != ledger.split_sha256:
        raise LedgerError("V-2: split.json changed after the freeze (its hash differs from run.json split_sha256)")


def check_metric(project_dir: Path, ledger: RunLedger) -> None:
    try:
        card = card_metric(project_dir)
    except ProjectError as err:
        raise LedgerError(f"V-3: {err}") from err
    prefix = f"{card.key} ({card.goal})"
    if not ledger.metric.startswith(prefix):
        raise LedgerError(f"V-3: run.json metric must start with {prefix!r}, the card's metric")
