"""What a candidate is. Pure: no I/O client, no Hydra."""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

Row = Mapping[str, object]


class Candidate(Protocol):
    def predict(self, row: Row) -> float: ...


@dataclass(frozen=True)
class Constant:
    value: float

    def predict(self, row: Row) -> float:
        return self.value


def config_sha256(model: Mapping[str, object]) -> str:
    """Train tags it on each child and eval recomputes it from the composed model: the two must agree (U-27)."""
    text = json.dumps(model, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
