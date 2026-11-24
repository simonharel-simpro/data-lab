"""Ledger I/O, filesystem checks and the hook CLI: `python -m datalab.ledger validate PATH...`."""

import json
import os
import secrets
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from datalab.ledger_access import look_number, record_test_look, test_access_allowed, test_access_problem
from datalab.ledger_checks import SPLIT_JSON, check_artifacts, check_metric, check_split_hash
from datalab.ledger_model import (
    Contract,
    Dataset,
    Decision,
    Kind,
    LedgerError,
    LogEntry,
    MilestoneEntry,
    RunLedger,
    Status,
    TestLook,
    Winner,
    contract,
    describe,
)
from datalab.ledger_ops import (
    decide,
    freeze_split,
    new_ledger,
    produce,
    record_data,
    redo,
    revalidate,
)
from datalab.split import Partition, Split, SplitError, SplitStrategy, partition, read_split, split_sha256

__all__ = [
    "Contract", "Dataset", "Decision", "Kind", "LedgerError", "LogEntry", "MilestoneEntry", "Partition",
    "RunLedger", "Split", "SplitError", "SplitStrategy", "Status", "TestLook", "Winner", "check_split_hash",
    "contract", "decide", "freeze_split", "look_number", "main", "new_ledger", "parse", "partition", "produce",
    "read", "read_split", "record_data", "record_test_look", "redo", "split_sha256", "test_access_allowed",
    "test_access_problem", "validate_dir", "write_atomic",
]  # fmt: skip

RUN_JSON: Final = "run.json"
_BOM: Final = "\N{ZERO WIDTH NO-BREAK SPACE}"


def parse(text: str) -> RunLedger:
    """Check order (1)-(4): JSON, `kind` present, field errors, then invariants I-1..I-15."""
    text = text.removeprefix(_BOM)
    try:
        doc = json.loads(text)
    except ValueError as err:
        raise LedgerError(f"invalid JSON: {err}") from err
    if isinstance(doc, dict) and "kind" not in doc:
        raise LedgerError("unsupported schema (kind missing)")
    try:
        return RunLedger.model_validate_json(text)
    except ValidationError as err:
        raise LedgerError(describe(err)) from err


def read(project_dir: Path) -> RunLedger:
    path = project_dir / RUN_JSON
    try:
        return parse(path.read_text(encoding="utf-8"))
    except LedgerError as err:
        raise LedgerError(f"{path}: {err}") from err
    except (OSError, UnicodeDecodeError) as err:
        raise LedgerError(f"{path}: cannot read: {err}") from err


def _check_overwrite(project_dir: Path, new: RunLedger, replace_corrupt: bool, base: RunLedger | None) -> None:
    try:
        old = read(project_dir)
    except LedgerError:
        if replace_corrupt:
            return
        raise
    # The truly simultaneous window (this check, then os.replace) stays open and is accepted: data-lab is
    # single-user; this closes the stale-read case.
    if base is not None and old != base:
        raise LedgerError("run.json changed since it was read: re-read it and apply the change again")
    if new.decisions_log[: len(old.decisions_log)] != old.decisions_log:
        raise LedgerError("decisions_log is append-only: the new ledger rewrites an earlier entry")
    if new.test_looks[: len(old.test_looks)] != old.test_looks:
        raise LedgerError("test_looks is append-only: the new ledger rewrites an earlier look")
    if old.milestones["scoping"].status is Status.VALIDATED and old.kind is not new.kind:
        raise LedgerError(f"kind is fixed once scoping is validated ({old.kind}): archive run.json first")


def _fsync_dir(folder: Path) -> None:
    if os.name != "posix":
        return
    fd = os.open(folder, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _publish(path: Path, text: str) -> None:
    tmp = path.with_name(f"run.{secrets.token_hex(4)}.json.tmp")
    try:
        with tmp.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        _fsync_dir(path.parent)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def write_atomic(
    project_dir: Path, ledger: RunLedger, *, base: RunLedger | None = None, replace_corrupt: bool = False
) -> None:
    checked = revalidate(ledger.model_dump(mode="json"))
    path = project_dir / RUN_JSON
    if path.exists():
        _check_overwrite(project_dir, checked, replace_corrupt, base)
    doc = checked.model_dump(mode="json")
    doc["milestones"] = {m: doc["milestones"][m] for m in checked.sequence()}
    _publish(path, json.dumps(doc, indent=2, ensure_ascii=False) + "\n")


def validate_dir(project_dir: Path) -> None:
    if (project_dir / SPLIT_JSON).is_file():
        try:
            read_split(project_dir / SPLIT_JSON)
        except SplitError as err:
            raise LedgerError(str(err)) from err
    if (project_dir / RUN_JSON).exists():
        ledger = read(project_dir)
        check_artifacts(project_dir, ledger)
        check_split_hash(project_dir, ledger)
        check_metric(project_dir, ledger)


class _UsageError(Exception):
    pass


def _dirs_of(paths: Sequence[str]) -> list[Path]:
    dirs: set[Path] = set()
    for raw in paths:
        path = Path(raw).resolve()
        if path.is_dir():
            dirs.add(path)
        elif path.name in (RUN_JSON, SPLIT_JSON):
            dirs.add(path.parent)
        else:
            raise _UsageError(f"{raw}: not a project directory, run.json or split.json")
    missing = sorted(d for d in dirs if not d.is_dir())
    if missing:
        raise _UsageError(f"no such directory: {missing[0]}")
    return sorted(dirs)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if len(args) < 2 or args[0] != "validate":
            raise _UsageError("usage: python -m datalab.ledger validate PATH...")
        dirs = _dirs_of(args[1:])
    except _UsageError as err:
        print(err, file=sys.stderr)
        return 2
    failed = False
    for folder in dirs:
        try:
            validate_dir(folder)
        except LedgerError as err:
            print(f"FAIL {folder}: {err}", file=sys.stderr)
            failed = True
        else:
            print(f"ok {folder}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
