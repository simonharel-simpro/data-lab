"""`uv run python -m voice_arch.runner --arch a|b|c [--personas id,...] [--reps N]`: one sweep = one MLflow run (D-9).

Run one sweep at a time per OpenRouter key: the cost of a sweep is the key's usage delta (D-6).
"""

import argparse
import asyncio
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from types import TracebackType
from typing import Final, Protocol, Self

import mlflow
from mlflow import MlflowClient

from datalab.project import Project, load
from datalab.settings import Settings
from datalab.tracking import preflight, tracked_run
from voice_arch.arch import Arch
from voice_arch.budget import ESTIMATES_USD, BudgetExceeded, check_budget, spent_so_far
from voice_arch.call import CallRow, Outcome, run_one_call
from voice_arch.call_env import CallEnv
from voice_arch.livekit_env import LiveKitCallEnv
from voice_arch.openrouter_key import SpendTracker
from voice_arch.personas import Behaviour, Persona, load_personas
from voice_arch.scoring import FULL_REPS, aggregate, cost_per_call
from voice_arch.settings import VoiceSettings
from voice_arch.sweep_log import append_row, static_params, worker_params
from voice_arch.sweep_query import last_full_sweep_cost

logger = logging.getLogger(__name__)
MAX_CALLER_FAULT_PERCENT: Final = 10


class CallerFaultRate(Exception):
    pass


class Tracker(Protocol):
    def __enter__(self) -> Self: ...

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None: ...

    def spent_now(self) -> float | None: ...


class TrackerFactory(Protocol):
    def __call__(self, api_key: str, /, *, on_exit: Callable[[float], None]) -> Tracker: ...


@dataclass
class _Sweep:
    env: CallEnv
    personas: Sequence[Persona]
    arch: Arch
    reps: int
    settings: VoiceSettings
    results: Path
    spent: float
    rows: list[CallRow] = field(default_factory=list)

    def _check_spend(self, tracker: Tracker, index: int, *, last: bool) -> None:
        now = tracker.spent_now()
        if now is None:
            logger.warning("OpenRouter key usage unreadable: the budget cannot be checked after this call")
            mlflow.set_tag("cost_unknown", "true")
            return
        mlflow.log_metric("cost_usd", now, step=index)  # cumulative: a killed sweep loses at most one call's cost
        if not last and self.spent + now >= self.settings.experiment_budget_usd:  # a finished sweep is never failed
            raise BudgetExceeded(self.spent + now, self.settings.experiment_budget_usd)

    async def calls(self, run_id: str, tracker: Tracker) -> None:
        plan = [(p, rep) for p in self.personas for rep in range(self.reps)]
        for index, (persona, rep) in enumerate(plan):
            row = await run_one_call(
                self.env, persona, self.arch, run_id, rep,
                call_timeout_s=self.settings.call_timeout_s, join_timeout_s=self.settings.agent_join_timeout_s,
            )  # fmt: skip
            self.rows.append(row)
            append_row(self.results, row)
            logger.info("%s rep %d: %s exact=%s", persona.id, rep, row.outcome.value, row.exact)
            self._check_spend(tracker, index, last=index + 1 == len(plan))

    def log_summary(self, full: bool) -> None:
        mlflow.log_params(worker_params(self.rows))
        mlflow.log_metrics(aggregate(self.rows, full=full))
        mlflow.log_dict([row.model_dump(mode="json") for row in self.rows], "per_conversation.json")
        faults = sum(r.outcome is Outcome.CALLER_FAULT for r in self.rows)
        if faults * 100 > MAX_CALLER_FAULT_PERCENT * len(self.rows):
            raise CallerFaultRate(f"{faults} of {len(self.rows)} calls failed on the caller's side (F-6)")


async def run_sweep(  # the plan fixes this signature
    env: CallEnv,
    personas: Sequence[Persona],
    arch: Arch,
    reps: int,
    settings: VoiceSettings,
    *,
    project: Project,
    dl_settings: Settings,
    spent: float,
    last_full_cost: Callable[[], float | None],
    spend_tracker: TrackerFactory,
) -> str:
    """Budget gate (F-4b), then the whole sweep inside one run; any raise leaves the run FAILED, rows kept."""
    estimate = last_full_cost()
    check_budget(
        spent, ESTIMATES_USD["conversations"] if estimate is None else estimate, settings.experiment_budget_usd
    )
    sweep = _Sweep(env, personas, arch, reps, settings, project.root / "results", spent)
    full = len({p.id for p in personas}) == len(Behaviour) and reps == FULL_REPS
    tags = {"full": str(full).lower(), "arch": arch.value}

    def on_exit(cost: float) -> None:
        mlflow.log_metric("cost_usd", cost, step=len(sweep.rows))  # after every per-call step (S-15a)
        if (per_call := cost_per_call(cost, sweep.rows)) is not None:
            mlflow.log_metric("cost_per_call_usd", per_call)

    key = settings.openrouter_api_key.get_secret_value()
    with (
        tracked_run(project, dl_settings, run_name=f"arch-{arch.value}", sub="conversations", tags=tags) as run_id,
        spend_tracker(key, on_exit=on_exit) as tracker,
    ):
        sweep.results = sweep.results / f"{run_id}.jsonl"
        mlflow.log_params(static_params(arch, personas, reps, settings))
        await sweep.calls(run_id, tracker)
        sweep.log_summary(full)
    return run_id


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="voice_arch.runner", description="Run one sweep against the simulated caller."
    )
    parser.add_argument("--arch", choices=[a.value for a in Arch], required=True)
    parser.add_argument("--personas", help="comma-separated persona ids (default: all six)")
    parser.add_argument("--reps", type=int, default=FULL_REPS, help=f"repetitions per persona (default {FULL_REPS})")
    args = parser.parse_args(argv)
    if args.reps < 1:
        parser.error("--reps must be at least 1")
    return args


def _select(personas: list[Persona], wanted: str | None) -> list[Persona]:
    if wanted is None:
        return personas
    ids = [i.strip() for i in wanted.split(",")]
    unknown = sorted(set(ids) - {p.id for p in personas})
    if unknown:
        raise SystemExit(f"unknown persona id(s) {', '.join(unknown)}; known: {', '.join(p.id for p in personas)}")
    return [p for p in personas if p.id in ids]


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    logging.basicConfig(level=logging.INFO)
    voice = VoiceSettings()  # pyright: ignore[reportCallIssue]
    project, dl = load(), Settings()
    preflight(dl.mlflow_tracking_uri)  # every config is validated before any LiveKit I/O
    personas = _select(load_personas(project.root / "data" / "personas.jsonl"), args.personas)
    client = MlflowClient(dl.mlflow_tracking_uri)
    run_id = asyncio.run(
        run_sweep(
            LiveKitCallEnv(voice),
            personas,
            Arch(args.arch),
            args.reps,
            voice,
            project=project,
            dl_settings=dl,
            spent=spent_so_far(dl),
            last_full_cost=partial(last_full_sweep_cost, client),
            spend_tracker=SpendTracker,
        )
    )
    print(run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
