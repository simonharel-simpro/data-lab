"""The frozen split (`split.json`, trouvetou schema + data-lab rules) and its hash. Pure: no mlflow/weaviate."""

import hashlib
from datetime import datetime
from enum import StrEnum
from itertools import pairwise
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, NonNegativeInt, ValidationError, field_validator, model_validator
from pydantic_core import PydanticCustomError


class Partition(StrEnum):
    TRAIN = "train"
    VAL = "val"
    TEST = "test"


class SplitStrategy(StrEnum):
    RANDOM = "random"
    STRATIFIED = "stratified"
    TEMPORAL = "temporal"
    GROUPED = "grouped"


class SplitError(ValueError):
    """A bad split; the message names the file when there is one."""


class _Frozen(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class GroupBound(_Frozen):
    groups: tuple[str, ...]


class TimeBound(_Frozen):
    time_max: str

    @field_validator("time_max")
    @classmethod
    def _parses(cls, value: str) -> str:
        try:
            datetime.fromisoformat(value)
        except ValueError as err:
            raise ValueError(f"time_max {value!r} is not an ISO 8601 date") from err
        return value


PartitionSpec = tuple[NonNegativeInt, ...] | GroupBound | TimeBound


class Splits(_Frozen):
    train: PartitionSpec
    val: PartitionSpec
    test: PartitionSpec


class Split(_Frozen):
    strategy: SplitStrategy
    seed: int
    target: str
    group_key: str | None
    time_col: str | None
    splits: Splits

    @model_validator(mode="after")
    def _rules(self) -> Self:
        problem = _first_problem(self)
        if problem is not None:
            raise PydanticCustomError("split_invariant", "{msg}", {"msg": problem})
        return self


def _members(spec: PartitionSpec) -> tuple[str | int, ...]:
    if isinstance(spec, GroupBound):
        return spec.groups
    if isinstance(spec, TimeBound):
        return ()
    return spec


def _is_empty(spec: PartitionSpec) -> bool:
    return not isinstance(spec, TimeBound) and not _members(spec)


def _shape_problem(split: Split, specs: dict[Partition, PartitionSpec]) -> str | None:
    shapes = {type(spec) for spec in specs.values()}
    if len(shapes) > 1:
        return "partitions mix shapes: all of train, val, test must be index lists, group bounds or time bounds"
    if GroupBound in shapes and (split.strategy is not SplitStrategy.GROUPED or split.group_key is None):
        return "group bounds need strategy 'grouped' and a group_key"
    if TimeBound in shapes and (split.strategy is not SplitStrategy.TEMPORAL or split.time_col is None):
        return "time bounds need strategy 'temporal' and a time_col"
    if split.strategy is SplitStrategy.GROUPED and split.group_key is None:
        return "strategy 'grouped' needs a group_key"
    return None


def _overlap_problem(specs: dict[Partition, PartitionSpec]) -> str | None:
    seen: dict[str | int, Partition] = {}
    for which, spec in specs.items():
        members = _members(spec)
        if len(set(members)) != len(members):
            return f"{which} lists a duplicate entry"
        for member in members:
            if member in seen:
                return f"{member!r} is in both {seen[member]} and {which}"
            seen[member] = which
    return None


def _time_problem(specs: dict[Partition, PartitionSpec]) -> str | None:
    bounds = [spec.time_max for spec in specs.values() if isinstance(spec, TimeBound)]
    if not bounds:
        return None
    try:
        parsed = [datetime.fromisoformat(bound) for bound in bounds]
        increasing = all(a < b for a, b in pairwise(parsed))
    except TypeError:
        return "time_max values mix timezone-aware and naive dates"
    return None if increasing else "time_max must strictly increase from train to val to test"


def _first_problem(split: Split) -> str | None:
    specs = {which: getattr(split.splits, which.value) for which in Partition}
    problem = _shape_problem(split, specs) or _overlap_problem(specs) or _time_problem(specs)
    if problem is not None:
        return problem
    for which in (Partition.TRAIN, Partition.TEST):
        if _is_empty(specs[which]):
            return f"{which} must not be empty"
    return None


def read_split(path: Path) -> Split:
    try:
        text = path.read_bytes().decode("utf-8-sig")
        return Split.model_validate_json(text)
    except (OSError, UnicodeDecodeError) as err:
        raise SplitError(f"{path}: cannot read: {err}") from err
    except ValidationError as err:
        first = err.errors()[0]
        loc = ".".join(str(part) for part in first["loc"])
        raise SplitError(f"{path}: {loc + ': ' if loc else ''}{first['msg']}") from err


def split_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def partition(split: Split, which: Partition) -> PartitionSpec:
    return getattr(split.splits, which.value)
