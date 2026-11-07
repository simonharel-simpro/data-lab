"""The score and the metric-key rules. Pure."""

import re
from collections.abc import Collection, Mapping, Sequence
from typing import Final

_TOKEN_SPLIT: Final = re.compile(r"[._/-]")


def score(predictions: Sequence[float], labels: Sequence[float]) -> float:
    """Minus the mean absolute error, so higher is better (card goal `max`)."""
    if not predictions:
        raise ValueError("cannot score an empty partition")
    if len(predictions) != len(labels):
        raise ValueError(f"length mismatch: {len(predictions)} predictions for {len(labels)} labels")
    return -sum(abs(p - y) for p, y in zip(predictions, labels, strict=True)) / len(labels)


def metric_key_problems(
    child_keys: Mapping[str, frozenset[str]], key: str, allowed: Collection[str], candidates: Collection[str]
) -> list[str]:
    """Finished children share one key set within {key, cost_usd, *allowed}; no key names a candidate (U-29)."""
    problems: list[str] = []
    if len(set(child_keys.values())) > 1:
        shown = {name: sorted(keys) for name, keys in sorted(child_keys.items())}
        problems.append(f"children log different metric keys: {shown}")
    seen = sorted(set().union(*child_keys.values()))
    extra = [k for k in seen if k not in {key, "cost_usd", *allowed}]
    if extra:
        problems.append(f"metric keys not allowed (declare them in experiment.metrics): {extra}")
    named = [k for k in seen if any(token in candidates for token in _TOKEN_SPLIT.split(k))]
    if named:
        problems.append(f"metric keys carry a candidate name as a token: {named}")
    return problems
