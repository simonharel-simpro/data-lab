import json
from pathlib import Path

import pytest

from datalab.split import Partition, SplitError

# The package name varies per project and would sort differently against `datalab`: sort the two apart.
# isort: split
from __DATALAB_PACKAGE__.grid import expand
from __DATALAB_PACKAGE__.scoring import label, metric_key_problems, score
from __DATALAB_PACKAGE__.split import load_split, read_rows

from .conftest import FIXTURES


def _write(folder: Path, split: dict[str, object]) -> Path:
    folder.mkdir(exist_ok=True)
    base = {"strategy": "random", "seed": 0, "target": "y", "group_key": None, "time_col": None}
    (folder / "split.json").write_text(json.dumps(base | split), encoding="utf-8")
    return folder


def _rows(n: int) -> list[dict[str, object]]:
    return [{"x": i, "y": 0.0} for i in range(n)]


def test_label_reads_numbers_and_numeric_strings() -> None:
    assert label({"y": 2}, "y") == 2.0
    assert label({"y": "1.5"}, "y") == 1.5


def test_label_rejects_missing_none_and_non_numeric() -> None:
    with pytest.raises(KeyError):
        label({"x": 1}, "y")
    with pytest.raises(TypeError):
        label({"y": None}, "y")
    with pytest.raises(TypeError):
        label({"y": [1]}, "y")
    with pytest.raises(ValueError, match="abc"):
        label({"y": "abc"}, "y")


def test_score_rejects_empty_or_unequal() -> None:
    with pytest.raises(ValueError, match="empty"):
        score([], [])
    with pytest.raises(ValueError, match="length"):
        score([1.0], [1.0, 2.0])
    assert score([0.0, 1.0], [1.0, 1.0]) == -0.5


def test_read_rows_bad_line_names_it(tmp_path: Path) -> None:
    path = tmp_path / "d.jsonl"
    path.write_text('{"x": 1}\n{"x":\n', encoding="utf-8")

    with pytest.raises(ValueError, match="line 2"):
        read_rows(path)


def test_load_split_index_out_of_range(tmp_path: Path) -> None:
    folder = _write(tmp_path / "e", {"splits": {"train": [0, 9], "val": [3, 4], "test": [5, 6]}})

    with pytest.raises(SplitError):
        load_split(folder, [Partition.TRAIN], rows=_rows(7))


def test_load_split_index_split_not_covering_rows_rejected(tmp_path: Path) -> None:
    short = _write(tmp_path / "a", {"splits": {"train": [0, 1, 2], "val": [3, 4], "test": [5]}})
    long = _write(tmp_path / "b", {"splits": {"train": [0, 1, 2], "val": [3, 4], "test": [5, 6, 7]}})

    with pytest.raises(SplitError):
        load_split(short, [Partition.TRAIN], rows=_rows(7))
    with pytest.raises(SplitError):
        load_split(long, [Partition.TRAIN], rows=_rows(7))
    ok = load_split(FIXTURES, [Partition.TRAIN], rows=_rows(7))
    assert [r["x"] for r in ok[Partition.TRAIN]] == [0, 1, 2]


def test_load_split_grouped_rows(tmp_path: Path) -> None:
    splits = {"train": {"groups": ["a"]}, "val": {"groups": ["b"]}, "test": {"groups": ["c"]}}
    folder = _write(tmp_path / "g", {"strategy": "grouped", "group_key": "g", "splits": splits})
    rows = [{"g": "a"}, {"g": "b"}, {"g": "a"}, {"g": "c"}]

    parts = load_split(folder, [Partition.TRAIN, Partition.VAL], rows=rows)

    assert parts[Partition.TRAIN] == [rows[0], rows[2]]
    assert parts[Partition.VAL] == [rows[1]]
    assert Partition.TEST not in parts


def test_load_split_temporal_rows(tmp_path: Path) -> None:
    splits = {
        "train": {"time_max": "2024-01-31"},
        "val": {"time_max": "2024-02-29"},
        "test": {"time_max": "2024-03-31"},
    }
    folder = _write(tmp_path / "t", {"strategy": "temporal", "time_col": "t", "splits": splits})
    rows = [{"t": "2024-01-15"}, {"t": "2024-02-10"}, {"t": "2024-03-01"}]

    dev = load_split(folder, [Partition.TRAIN, Partition.VAL], rows=rows)
    full = load_split(folder, [Partition.TEST], rows=rows, allow_test=True)

    assert dev == {Partition.TRAIN: [rows[0]], Partition.VAL: [rows[1]]}
    assert full == {Partition.TEST: [rows[2]]}


def test_grid_expand_order() -> None:
    combos = expand(["a", "b"], {"a": {"y": [1, 2], "x": [0]}})

    assert [(c.run_name, dict(c.params)) for c in combos] == [
        ("a-0", {"x": 0, "y": 1}),
        ("a-1", {"x": 0, "y": 2}),
        ("b-0", {}),
    ]


def test_grid_expand_sorts_param_names_before_the_product() -> None:
    combos = expand(["a"], {"a": {"y": [1, 2], "x": [0, 1]}})

    assert [(c.index, c.params["x"], c.params["y"]) for c in combos] == [(0, 0, 1), (1, 0, 2), (2, 1, 1), (3, 1, 2)]


def test_metric_key_problems() -> None:
    children = {
        "a-0": frozenset({"score", "cost_usd"}),
        "b-0": frozenset({"score", "cost_usd", "b_acc"}),
    }

    problems = metric_key_problems(children, "score", [], ["a", "b"])

    assert len(problems) == 3
    assert "differ" in problems[0]
    assert "not allowed" in problems[1] and "b_acc" in problems[1]
    assert "candidate" in problems[2] and "b_acc" in problems[2]
    assert metric_key_problems({"core-0": frozenset({"score", "cost_usd"})}, "score", [], ["core"]) == []
