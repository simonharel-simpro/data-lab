"""Pure helpers of the stage-1 bench: item selection, metric slugs, crash-copy sink, MLflow recording."""

import dataclasses
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import mlflow

from voice_arch.winners import Choice, LlmRow, SttRow, TtsRow

type Row = SttRow | TtsRow | LlmRow
type Emit = Callable[[Row], None]


@dataclass(frozen=True)
class Outcome:
    metrics: Mapping[str, float]
    choice: Choice | None
    reason: str
    params: Mapping[str, str | int]


def select[T](items: list[T], n: int | None) -> list[T]:
    """The first `n` items; `n` outside 1..len is refused, never clamped."""
    if n is None:
        return items
    if not 1 <= n <= len(items):
        raise ValueError(f"n must be between 1 and {len(items)}, got {n}")
    return items[:n]


def slug(model: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "_", model)


def appender(sink: Path) -> Emit:
    """Each row is appended at once: the crash copy survives a failing later candidate or an MLflow outage."""
    sink.parent.mkdir(parents=True, exist_ok=True)

    def emit(row: Row) -> None:
        with sink.open("a", encoding="utf-8") as f:
            f.write(json.dumps(dataclasses.asdict(row)) + "\n")

    return emit


def record_outcome(outcome: Outcome) -> None:
    mlflow.log_params(dict(outcome.params))
    mlflow.log_metrics(dict(outcome.metrics))
    mlflow.set_tags({"winner": outcome.choice.model if outcome.choice else "none", "winner_reason": outcome.reason})
