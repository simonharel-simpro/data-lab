"""Read the data file and cut it by the frozen split.json; the test partition needs an explicit opt-in (U-3)."""

import json
from collections.abc import Collection, Sequence
from datetime import datetime
from pathlib import Path

from datalab.split import GroupBound, Partition, PartitionSpec, Split, SplitError, TimeBound, partition, read_split

from .candidates import Row


class SplitAccessError(RuntimeError):
    pass


def read_rows(path: Path) -> list[Row]:
    rows: list[Row] = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as err:
            raise ValueError(f"{path}: line {number} is not valid JSON: {err}") from err
        if not isinstance(row, dict):
            raise ValueError(f"{path}: line {number} is not a JSON object")
        rows.append(row)
    return rows


def _check_coverage(split: Split, count: int, path: Path) -> None:
    lists = [partition(split, which) for which in Partition]
    if not all(isinstance(spec, tuple) for spec in lists):
        return
    indices = [i for spec in lists if isinstance(spec, tuple) for i in spec]
    if any(i >= count for i in indices):
        raise SplitError(f"{path}: an index is out of range for {count} rows")
    if sorted(indices) != list(range(count)):
        raise SplitError(f"{path}: split.json does not cover data_file row for row ({count} rows)")


def _when(row: Row, column: str) -> datetime:
    try:
        return datetime.fromisoformat(str(row[column]))
    except (KeyError, ValueError) as err:
        raise SplitError(f"row has no ISO 8601 value in {column!r}: {row!r}") from err


def _pick(split: Split, which: Partition, spec: PartitionSpec, rows: Sequence[Row]) -> list[Row]:
    if isinstance(spec, tuple):
        return [rows[i] for i in spec]
    if isinstance(spec, GroupBound):
        key = split.group_key or ""
        return [r for r in rows if str(r.get(key)) in spec.groups]
    column = split.time_col or ""
    # A bound is read as that instant: a date-only time_max "2024-01-31" is midnight, so later rows of that day
    # fall in the next partition.
    order = list(Partition)
    before = order.index(which) - 1
    previous = partition(split, order[before]) if before >= 0 else None
    low = datetime.fromisoformat(previous.time_max) if isinstance(previous, TimeBound) else None
    high = datetime.fromisoformat(spec.time_max)
    return [r for r in rows if (low is None or low < _when(r, column)) and _when(r, column) <= high]


def load_split(
    experiment_dir: Path, partitions: Collection[Partition], *, rows: Sequence[Row], allow_test: bool = False
) -> dict[Partition, list[Row]]:
    if Partition.TEST in partitions and not allow_test:
        raise SplitAccessError("the test partition is read by eval only, at the audit (U-3)")
    path = experiment_dir / "split.json"
    if not path.is_file():
        raise FileNotFoundError(f"{path} not found: freeze the split first (/experiment)")
    split = read_split(path)
    _check_coverage(split, len(rows), path)
    return {which: _pick(split, which, partition(split, which), rows) for which in Partition if which in partitions}
