"""Sweep metrics from the call rows (pure). `exact_rate` is the experiment's metric (D-15)."""

import statistics
from collections.abc import Sequence
from typing import Final

from voice_arch.booking.record import SCORED_FIELDS
from voice_arch.call import CallRow, Outcome

FULL_REPS: Final = 5
# The calls that count in a rate: a timeout or a lost agent is a miss, a caller fault is not the arch's doing (F-6).
_COUNTED: Final = frozenset({Outcome.SCORED, Outcome.TIMEOUT, Outcome.AGENT_LOST})


def _counted(rows: Sequence[CallRow]) -> list[CallRow]:
    return [r for r in rows if r.outcome in _COUNTED]


def _rates(rows: Sequence[CallRow]) -> dict[str, float]:
    counted = _counted(rows)
    if not counted:
        return {}
    rates = {"exact_rate": sum(r.exact for r in counted) / len(counted)}
    for field in SCORED_FIELDS:
        rates[f"field_{field}_acc"] = sum(r.per_field.get(field, False) for r in counted) / len(counted)
    return rates


def _latency(rows: Sequence[CallRow]) -> dict[str, float]:
    turns = [t for r in rows for t in r.latencies]
    measured = [t for t in turns if t is not None]
    metrics: dict[str, float] = {"latency_turns": len(measured), "latency_turns_missing": len(turns) - len(measured)}
    if len(measured) == 1:
        metrics |= {"latency_p50_s": measured[0], "latency_p90_s": measured[0]}
    elif measured:
        deciles = statistics.quantiles(measured, n=10, method="inclusive")
        metrics |= {"latency_p50_s": deciles[4], "latency_p90_s": deciles[8]}
    return metrics


def _naturalness(rows: Sequence[CallRow]) -> dict[str, float]:
    turns = sum(r.agent_turns for r in rows)
    metrics = {
        "barge_ins": sum(r.barge_ins for r in rows),
        "barge_ins_handled": sum(r.barge_ins_handled for r in rows),
        "long_silences": sum(r.long_silences for r in rows),
        "session_errors": sum(r.session_errors for r in rows),
    }
    out = {key: float(value) for key, value in metrics.items()}
    if turns:
        out["long_silences_per_turn"] = metrics["long_silences"] / turns
    return out


def aggregate(rows: Sequence[CallRow], *, full: bool) -> dict[str, float]:
    """Every key is prefixed `smoke_` unless this is the full sweep, so a smoke never stands in for it (U-1)."""
    metrics = _rates(rows) | _latency(rows) | _naturalness(rows)
    metrics |= {f"n_{outcome.value}": float(sum(r.outcome is outcome for r in rows)) for outcome in Outcome}
    metrics["n_exact"] = float(sum(r.exact for r in _counted(rows)))
    prefix = "" if full else "smoke_"
    return {f"{prefix}{key}": value for key, value in metrics.items()}


def cost_per_call(cost_usd: float, rows: Sequence[CallRow]) -> float | None:
    """Cost over the same denominator as `exact_rate` (U-19); None when no call counts."""
    counted = _counted(rows)
    return cost_usd / len(counted) if counted else None
