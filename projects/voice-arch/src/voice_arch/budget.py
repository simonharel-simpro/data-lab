"""Software experiment budget (D-1, F-4b) over the shared OpenRouter key, summed from the MLflow runs."""

from typing import Final

from mlflow import MlflowClient
from mlflow.entities import ViewType

from datalab.project import experiment_name

# Money was spent whether or not the run finished.
_COUNTED_STATUSES: Final = frozenset({"FINISHED", "FAILED", "KILLED"})
_SUBS: Final = ("bench", "conversations")


class BudgetExceeded(Exception):
    def __init__(self, spent: float, budget: float) -> None:
        super().__init__(f"experiment budget reached: {spent:.2f} $ spent of {budget:.2f} $")
        self.spent = spent
        self.budget = budget


def spent_so_far(client: MlflowClient) -> float:
    """Sum of the latest `cost_usd` of every counted run of the voice-arch bench and conversations experiments."""
    total = 0.0
    for sub in _SUBS:
        experiment = client.get_experiment_by_name(experiment_name("voice-arch", sub))
        if experiment is None:
            continue
        token: str | None = None
        while True:
            # ALL: a soft-deleted run still spent its money.
            page = client.search_runs(
                [experiment.experiment_id], run_view_type=ViewType.ALL, max_results=1000, page_token=token
            )
            total += sum(run.data.metrics.get("cost_usd", 0.0) for run in page if run.info.status in _COUNTED_STATUSES)
            token = page.token
            if not token:
                break
    return total


def check_budget(spent: float, estimate: float, budget: float) -> None:
    """One rule everywhere: reaching the budget stops."""
    if spent + estimate >= budget:
        raise BudgetExceeded(spent, budget)
