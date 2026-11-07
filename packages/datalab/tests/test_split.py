import hashlib
import json
from pathlib import Path

import pytest

from datalab.split import GroupBound, Partition, SplitError, TimeBound, partition, read_split, split_sha256


def _split(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "strategy": "random",
        "seed": 0,
        "target": "y",
        "group_key": None,
        "time_col": None,
        "splits": {"train": [0, 1, 2], "val": [3], "test": [4]},
    }
    return base | overrides


def _write(tmp_path: Path, data: dict[str, object]) -> Path:
    path = tmp_path / "split.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _splits(train: object, val: object, test: object) -> dict[str, object]:
    return {"train": train, "val": val, "test": test}


def test_f_4_overlapping_groups_rejected(tmp_path: Path) -> None:
    data = _split(
        strategy="grouped",
        group_key="persona",
        splits=_splits({"groups": ["a", "b"]}, {"groups": []}, {"groups": ["b"]}),
    )

    with pytest.raises(SplitError, match="b"):
        read_split(_write(tmp_path, data))


def test_f_4_grouped_and_temporal_shapes_accepted(tmp_path: Path) -> None:
    grouped = _split(
        strategy="grouped",
        group_key="persona",
        splits=_splits({"groups": ["a"]}, {"groups": ["b"]}, {"groups": ["c"]}),
    )
    temporal = _split(
        strategy="temporal",
        time_col="t",
        splits=_splits({"time_max": "2024-01-01"}, {"time_max": "2024-06-01"}, {"time_max": "2024-12-31"}),
    )

    assert partition(read_split(_write(tmp_path, grouped)), Partition.TEST) == GroupBound(groups=("c",))
    assert partition(read_split(_write(tmp_path, temporal)), Partition.VAL) == TimeBound(time_max="2024-06-01")


def test_overlapping_indices_rejected(tmp_path: Path) -> None:
    data = _split(splits=_splits([0, 1], [1], [4]))

    with pytest.raises(SplitError, match=r"split\.json"):
        read_split(_write(tmp_path, data))


def test_temporal_bounds_not_increasing_rejected(tmp_path: Path) -> None:
    data = _split(
        strategy="temporal",
        time_col="t",
        splits=_splits({"time_max": "2024-01-01"}, {"time_max": "2024-12-31"}, {"time_max": "2024-12-31"}),
    )

    with pytest.raises(SplitError):
        read_split(_write(tmp_path, data))


def test_empty_test_rejected(tmp_path: Path) -> None:
    with pytest.raises(SplitError):
        read_split(_write(tmp_path, _split(splits=_splits([0, 1], [2], []))))

    split = read_split(_write(tmp_path, _split(splits=_splits([0, 1], [], [2]))))

    assert partition(split, Partition.VAL) == ()


def test_mixed_shapes_rejected(tmp_path: Path) -> None:
    data = _split(strategy="grouped", group_key="g", splits=_splits([0, 1], {"groups": ["b"]}, {"groups": ["c"]}))

    with pytest.raises(SplitError):
        read_split(_write(tmp_path, data))


def test_grouped_without_group_key_rejected(tmp_path: Path) -> None:
    with pytest.raises(SplitError, match="group_key"):
        read_split(_write(tmp_path, _split(strategy="grouped", group_key=None)))


def test_split_sha256_is_raw_bytes_hash(tmp_path: Path) -> None:
    path = tmp_path / "split.json"
    path.write_bytes(b'{"x":1}')

    assert split_sha256(path) == hashlib.sha256(b'{"x":1}').hexdigest()


def test_read_split_strips_bom(tmp_path: Path) -> None:
    path = tmp_path / "split.json"
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps(_split()).encode("utf-8"))

    assert partition(read_split(path), Partition.TRAIN) == (0, 1, 2)


def test_split_seed_string_rejected(tmp_path: Path) -> None:
    with pytest.raises(SplitError):
        read_split(_write(tmp_path, _split(seed="0")))
