"""`uv run python -m voice_arch.runner --arch a|b|c [--personas id,...] [--reps N]`: one sweep = one MLflow run (D-9).

Run one sweep at a time per OpenRouter key: the cost of a sweep is the key's usage delta (D-6).
"""

import argparse
import asyncio
import logging
from functools import partial

import mlflow
from mlflow import MlflowClient

from datalab.project import load
from datalab.settings import Settings
from datalab.tracking import preflight, tracked_run
from voice_arch.arch import Arch
from voice_arch.budget import ESTIMATES_USD, check_budget, spent_so_far
from voice_arch.call_env import CallEnv
from voice_arch.livekit_env import LiveKitCallEnv
from voice_arch.openrouter_key import SpendTracker
from voice_arch.personas import Behaviour, Persona, load_personas
from voice_arch.scoring import FULL_REPS, cost_per_call
from voice_arch.settings import load_settings
from voice_arch.sweep import Sweep, SweepContext, SweepPlan
from voice_arch.sweep_log import static_params
from voice_arch.sweep_query import last_full_sweep_cost

logger = logging.getLogger(__name__)


def _open_sweep(env: CallEnv, plan: SweepPlan, ctx: SweepContext) -> tuple[Sweep, bool]:
    """Budget gate (F-4b), then the sweep state; the flag says whether this is the full persona x reps grid."""
    estimate = ctx.last_full_cost()
    check_budget(
        ctx.spent, ESTIMATES_USD["conversations"] if estimate is None else estimate, ctx.voice.experiment_budget_usd
    )
    sweep = Sweep(env, plan.personas, plan.arch, plan.reps, ctx.voice, ctx.project.root / "results", ctx.spent)
    return sweep, len({p.id for p in plan.personas}) == len(Behaviour) and plan.reps == FULL_REPS


async def run_sweep(env: CallEnv, plan: SweepPlan, ctx: SweepContext) -> str:
    """Budget gate, then the whole sweep inside one run; any raise leaves the run FAILED, rows kept."""
    sweep, full = _open_sweep(env, plan, ctx)
    tags = {"full": str(full).lower(), "arch": plan.arch.value}

    def on_exit(cost: float) -> None:
        mlflow.log_metric("cost_usd", cost, step=len(sweep.rows))  # after every per-call step (S-15a)
        if (per_call := cost_per_call(cost, sweep.rows)) is not None:
            mlflow.log_metric("cost_per_call_usd", per_call)

    key = ctx.voice.openrouter_api_key.get_secret_value()
    with (
        tracked_run(
            ctx.project, ctx.dl_settings, run_name=f"arch-{plan.arch.value}", sub="conversations", tags=tags
        ) as run_id,
        ctx.spend_tracker(key, on_exit=on_exit) as tracker,
    ):
        sweep.results = sweep.results / f"{run_id}.jsonl"
        mlflow.log_params(static_params(plan.arch, plan.personas, plan.reps, ctx.voice))
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
    voice = load_settings()
    project, dl = load(), Settings()
    preflight(dl.mlflow_tracking_uri)  # every config is validated before any LiveKit I/O
    personas = _select(load_personas(project.root / "data" / "personas.jsonl"), args.personas)
    client = MlflowClient(dl.mlflow_tracking_uri)
    plan = SweepPlan(personas, Arch(args.arch), args.reps)
    ctx = SweepContext(
        project=project,
        dl_settings=dl,
        voice=voice,
        spent=spent_so_far(dl),
        last_full_cost=partial(last_full_sweep_cost, client),
        spend_tracker=SpendTracker,
    )
    run_id = asyncio.run(run_sweep(LiveKitCallEnv(voice), plan, ctx))
    print(run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
