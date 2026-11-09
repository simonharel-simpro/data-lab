"""Hyper-parameter grids: one combination per child run. Pure."""

import itertools
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

Scalar = str | int | float | bool


class GridError(ValueError):
    pass


@dataclass(frozen=True)
class Combo:
    candidate: str
    index: int
    params: Mapping[str, Scalar]

    @property
    def run_name(self) -> str:
        return f"{self.candidate}-{self.index}"


def _values(candidate: str, param: str, values: object) -> list[Scalar]:
    if not isinstance(values, list | tuple) or not values:
        raise GridError(f"hparams_search.{candidate}.{param} must be a non-empty list, got {values!r}")
    items = cast("Sequence[object]", values)  # a non-empty list/tuple from parsed YAML: element types unknown
    bad = [v for v in items if not isinstance(v, str | int | float | bool)]
    if bad:
        raise GridError(f"hparams_search.{candidate}.{param} holds non-scalar values: {bad!r}")
    return cast("list[Scalar]", list(items))


def expand(candidates: Sequence[str], search: Mapping[str, Mapping[str, Sequence[Scalar]]]) -> list[Combo]:
    unknown = sorted(set(search) - set(candidates))
    if unknown:
        raise GridError(f"hparams_search names {unknown}, which are not in experiment.candidates {list(candidates)}")
    combos: list[Combo] = []
    for candidate in candidates:
        grid = search.get(candidate, {})
        names = sorted(grid)
        axes = [_values(candidate, name, grid[name]) for name in names]
        for index, values in enumerate(itertools.product(*axes)):
            combos.append(Combo(candidate, index, dict(zip(names, values, strict=True))))
    return combos
