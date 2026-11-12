"""Software experiment budget (D-1, F-4b) over the shared OpenRouter key, summed from the MLflow runs."""

import logging
from typing import Final, cast

from mlflow import MlflowClient
from mlflow.entities import Run, RunStatus, ViewType

from datalab.project import experiment_name
from datalab.settings import Settings
from datalab.tracking_queries import project_spend

logger = logging.getLogger(__name__)
PROJECT: Final = "voice-arch"
# What one run of each sub-experiment may cost: the F-4b gate's fallback, and what a run that crashed before it
# logged any cost counts for (P-2). A finished sweep is measured instead (`last_full_sweep_cost`).
ESTIMATES_USD: Final = {"conversations": 15.0, "bench": 2.0}
_PAGE = 1000
_FINISHED: Final = RunStatus.to_string(RunStatus.FINISHED)


class BudgetExceeded(Exception):
    def __init__(self, spent: float, budget: float) -> None:
        super().__init__(f"experiment budget reached: {spent:.2f} $ spent of {budget:.2f} $")
        self.spent = spent
        self.budget = budget


def _has_no_cost(run: Run) -> bool:
    if "cost_usd" in run.data.metrics:
        return False
    return run.info.status != _FINISHED or run.data.tags.get("cost_unknown") == "true"


def _unmeasured_estimates(client: MlflowClient) -> float:
    """Estimates of the runs that never logged a `cost_usd` and are not FINISHED (crashed, killed, still running)
    or are tagged `cost_unknown=true` (the key was unreadable, F-12)."""
    total = 0.0
    for sub, estimate in ESTIMATES_USD.items():
        experiment = client.get_experiment_by_name(experiment_name(PROJECT, sub))
        if experiment is None:
            continue
        token: str | None = None
        while True:
            page = client.search_runs(
                [experiment.experiment_id],
                filter_string=f"tags.project = '{PROJECT}'",
                run_view_type=ViewType.ALL,  # a soft-deleted run still spent its money
                max_results=_PAGE,
                page_token=token,
            )
            for run in page:
                if _has_no_cost(run):
                    logger.warning(
                        "run %s has no cost_usd (not finished, or cost unknown): counted at the %.2f $ estimate",
                        run.info.run_id,
                        estimate,
                    )
                    total += estimate
            token = cast("str | None", page.token)  # pyright: ignore[reportUnknownMemberType]  # PagedList.token
            if not token:
                break
    return total


def spent_so_far(settings: Settings) -> float:
    """Every dollar of the voice-arch project: `cost_usd` of all runs whatever their status, plus P-2 estimates."""
    client = MlflowClient(settings.mlflow_tracking_uri)
    return project_spend(PROJECT, settings) + _unmeasured_estimates(client)


def check_budget(spent: float, estimate: float, budget: float) -> None:
    """One rule everywhere: reaching the budget stops."""
    if spent + estimate >= budget:
        raise BudgetExceeded(spent, budget)
