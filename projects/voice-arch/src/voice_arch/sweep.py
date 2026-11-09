"""One sweep's state and per-call loop: the spend check after every call and the summary at the end."""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Final, Protocol, Self

import mlflow

from datalab.project import Project
from datalab.settings import Settings
from voice_arch.arch import Arch
from voice_arch.budget import BudgetExceeded
from voice_arch.call import CallRow, Outcome, run_one_call
from voice_arch.call_env import CallEnv
from voice_arch.personas import Persona
from voice_arch.scoring import aggregate
from voice_arch.settings import VoiceSettings
from voice_arch.sweep_log import append_row, worker_params

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


@dataclass(frozen=True)
class SweepPlan:
    """What the sweep runs."""

    personas: Sequence[Persona]
    arch: Arch
    reps: int


@dataclass(frozen=True)
class SweepContext:
    """Where the sweep runs and with what budget."""

    project: Project
    dl_settings: Settings
    voice: VoiceSettings
    spent: float
    last_full_cost: Callable[[], float | None]
    spend_tracker: TrackerFactory


@dataclass
class Sweep:
    env: CallEnv
    personas: Sequence[Persona]
    arch: Arch
    reps: int
    settings: VoiceSettings
    results: Path
    spent: float
    rows: list[CallRow] = field(default_factory=list[CallRow])

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
        per_conversation = [row.model_dump(mode="json") for row in self.rows]
        # mlflow's stub says `dict`; it logs a list as JSON just as well.
        mlflow.log_dict(per_conversation, "per_conversation.json")  # pyright: ignore[reportArgumentType]
        faults = sum(r.outcome is Outcome.CALLER_FAULT for r in self.rows)
        if faults * 100 > MAX_CALLER_FAULT_PERCENT * len(self.rows):
            raise CallerFaultRate(f"{faults} of {len(self.rows)} calls failed on the caller's side (F-6)")
