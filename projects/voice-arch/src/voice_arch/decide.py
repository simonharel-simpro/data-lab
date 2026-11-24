"""`python -m voice_arch.decide`: pick the architecture from the latest full sweeps (D-15, U-16, U-23).

Pure rule on integers (calls, never rates), so a one-call margin is not a float comparison.
"""

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from mlflow import MlflowClient

from datalab.settings import Settings
from datalab.tracking import TrackingUnavailable, preflight
from voice_arch.arch import Arch
from voice_arch.call import Outcome
from voice_arch.sweep_query import human_ratings, latest_full_metrics

MARGIN_CALLS: Final = 2  # archs within this many exact calls of the best tie, and latency then decides
READY_EXACT_PERCENT: Final = 90
READY_LATENCY_S: Final = 1.2


@dataclass(frozen=True)
class ArchSummary:
    arch: str
    exact: int
    n: int
    latency_p50_s: float | None
    cost_per_call_usd: float | None
    human_rating_mean: float | None

    @property
    def exact_rate(self) -> float:
        return self.exact / self.n if self.n else 0.0


@dataclass(frozen=True)
class Decision:
    winner: str
    ranking: list[ArchSummary]
    production_ready: bool
    reason: str


def _tie_key(s: ArchSummary) -> tuple[bool, float, bool, float, str]:
    """Lowest latency p50, then lowest cost; a missing value ranks last; the arch letter keeps it deterministic."""
    latency, cost = s.latency_p50_s, s.cost_per_call_usd
    return (latency is None, latency or 0.0, cost is None, cost or 0.0, s.arch)


def human_rating_mean(ratings: Sequence[int]) -> float | None:
    """Reported next to the decision, never ranking (U-23)."""
    return sum(ratings) / len(ratings) if ratings else None


def pick_arch(summaries: Sequence[ArchSummary]) -> Decision:
    if not summaries:
        raise ValueError("no arch summaries to decide on")
    best = max(s.exact for s in summaries)
    contenders = sorted((s for s in summaries if best - s.exact <= MARGIN_CALLS), key=_tie_key)
    others = sorted((s for s in summaries if best - s.exact > MARGIN_CALLS), key=lambda s: (-s.exact, *_tie_key(s)))
    ranking = [*contenders, *others]
    winner = ranking[0]
    ready = (
        winner.exact * 100 >= READY_EXACT_PERCENT * winner.n
        and winner.latency_p50_s is not None
        and winner.latency_p50_s < READY_LATENCY_S
    )
    how = (
        "wins the latency/cost tie-break (within 2 exact calls of the best)" if len(contenders) > 1 else "is most exact"
    )
    reason = f"arch {winner.arch} {how} with {winner.exact}/{winner.n} exact bookings"
    return Decision(winner.arch, ranking, ready, reason)


class SweepDataError(Exception):
    """A full sweep run lacks a metric `decide` needs: the run is not a valid input, never read as 0."""


def summary_from_metrics(arch: Arch, metrics: dict[str, float], ratings: Sequence[int]) -> ArchSummary:
    try:
        n = sum(round(metrics[f"n_{o.value}"]) for o in (Outcome.SCORED, Outcome.TIMEOUT, Outcome.AGENT_LOST))
        exact = round(metrics["n_exact"])
    except KeyError as err:
        raise SweepDataError(f"the latest full {arch.value} sweep has no metric {err}") from err
    return ArchSummary(
        arch=arch.value, exact=exact, n=n, latency_p50_s=metrics.get("latency_p50_s"),
        cost_per_call_usd=metrics.get("cost_per_call_usd"), human_rating_mean=human_rating_mean(ratings),
    )  # fmt: skip


def _fmt(value: float | None, spec: str) -> str:
    return "n/a" if value is None else format(value, spec)


def render(decision: Decision) -> str:
    lines = [
        "| Arch | Exact | Exact rate | Latency p50 (s) | Cost / call ($) | Human rating |",
        "|---|---|---|---|---|---|",
    ]
    for s in decision.ranking:
        lines.append(
            f"| {s.arch} | {s.exact}/{s.n} | {s.exact_rate:.1%} | {_fmt(s.latency_p50_s, '.2f')} "
            f"| {_fmt(s.cost_per_call_usd, '.3f')} | {_fmt(s.human_rating_mean, '.1f')} |"
        )
    ready = "meets" if decision.production_ready else "does NOT meet"
    verdict = f"The winner {ready} the bar (>= 90 % exact, p50 < 1.2 s)."
    return "\n".join([*lines, "", f"Winner: {decision.reason}.", verdict])


def main() -> int:
    settings = Settings()
    try:
        preflight(settings.mlflow_tracking_uri)
    except TrackingUnavailable as err:
        print(f"MLflow unavailable: {err}", file=sys.stderr)
        return 1
    client = MlflowClient(settings.mlflow_tracking_uri)
    summaries = [
        summary_from_metrics(arch, metrics, human_ratings(client, arch))
        for arch, metrics in latest_full_metrics(client).items()
    ]
    missing = [a.value for a in Arch if a.value not in {s.arch for s in summaries}]
    if not summaries:
        print("no FINISHED full sweep found in voice-arch/conversations", file=sys.stderr)
        return 1
    if missing:
        print(f"warning: no full sweep for arch {', '.join(missing)}: ranked without it", file=sys.stderr)
    print(render(pick_arch(summaries)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
