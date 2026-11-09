import itertools
import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from datalab.split import SplitError, TimeBound, read_split
from tests.test_split import _split, _splits, _write

_TEMPORAL = {"strategy": "temporal", "time_col": "t"}
_BOUNDS = ({"time_max": "2024-01-01"}, {"time_max": "2024-06-01"}, {"time_max": "2024-12-31"})

_CASES: list[tuple[dict[str, object], str]] = [
    (_split(splits=_splits([0, 0, 1], [2], [3])), "train lists a duplicate entry"),
    (
        _split(
            **_TEMPORAL,
            splits=_splits({"time_max": "2024-01-01T00:00:00+00:00"}, *_BOUNDS[1:]),
        ),
        "time_max values mix timezone-aware and naive dates",
    ),
    (_split(time_col="t", splits=_splits(*_BOUNDS)), "time bounds need strategy 'temporal' and a time_col"),
    (
        _split(group_key="g", splits=_splits({"groups": ["a"]}, {"groups": ["b"]}, {"groups": ["c"]})),
        "group bounds need strategy 'grouped' and a group_key",
    ),
    (_split(splits=_splits([], [1], [2])), "train must not be empty"),
    (_split(splits=_splits([-1, 0], [1], [2])), "Input should be greater than or equal to 0"),
]


@pytest.mark.parametrize(
    ("data", "rule"),
    _CASES,
    ids=["duplicate", "mixed-tz", "time-non-temporal", "group-non-grouped", "empty-train", "negative-index"],
)
def test_split_rule_rejects_with_its_own_message(tmp_path: Path, data: dict[str, object], rule: str) -> None:
    with pytest.raises(SplitError, match=re.escape(rule)):
        read_split(_write(tmp_path, data))


def test_non_iso_time_max_is_rejected_by_the_time_bound_rule() -> None:
    with pytest.raises(ValidationError, match=re.escape("time_max 'not-a-date' is not an ISO 8601 date")):
        TimeBound(time_max="not-a-date")


def test_non_iso_time_max_is_rejected_through_read_split(tmp_path: Path) -> None:
    data = _split(**_TEMPORAL, splits=_splits(_BOUNDS[0], {"time_max": "not-a-date"}, _BOUNDS[2]))

    # read_split reports errors()[0], the tuple-branch error of the union, not the ISO rule text (see report).
    with pytest.raises(SplitError, match=r"splits\.val"):
        read_split(_write(tmp_path, data))


def test_every_index_assignment_is_accepted_iff_train_and_test_nonempty(tmp_path: Path) -> None:
    path = tmp_path / "split.json"
    for assignment in itertools.product(("train", "val", "test", None), repeat=4):
        parts: dict[str, list[int]] = {"train": [], "val": [], "test": []}
        for index, name in enumerate(assignment):
            if name is not None:
                parts[name].append(index)
        path.write_text(json.dumps(_split(splits=parts)), encoding="utf-8")

        if not (parts["train"] and parts["test"]):
            with pytest.raises(SplitError, match=r"(train|test) must not be empty"):
                read_split(path)
            continue
        accepted = read_split(path)
        assert [list(getattr(accepted.splits, name)) for name in parts] == list(parts.values())

        parts["test"].append(parts["train"][0])
        path.write_text(json.dumps(_split(splits=parts)), encoding="utf-8")
        with pytest.raises(SplitError, match="in both train and test"):
            read_split(path)
